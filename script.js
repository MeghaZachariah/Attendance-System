// Smart Attendance UI
// - Uses file input (camera/upload) to pick an image
// - Sends image to backend at http://127.0.0.1:8000/attendance
// - Renders present/absent lists, allows toggling, and confirms save

const fileInput = document.getElementById('fileInput');
const uploadInput = document.getElementById('uploadInput');
const markBtn = document.getElementById('markBtn');
const previewContainer = document.getElementById('previewContainer');
const previewImage = document.getElementById('previewImage');
const attendanceSection = document.getElementById('attendanceSection');
const presentList = document.getElementById('presentList');
const absentList = document.getElementById('absentList');
const attDate = document.getElementById('attDate');
const attTotal = document.getElementById('attTotal');
const attClass = document.getElementById('attClass');
const overlay = document.getElementById('overlay');
const messageEl = document.getElementById('message');
const confirmBtn = document.getElementById('confirmBtn');
const registerSection = document.getElementById('registerSection');
const registerForm = document.getElementById('registerForm');
const regStudentId = document.getElementById('regStudentId');
const regImage = document.getElementById('regImage');
const regBtn = document.getElementById('regBtn');
const regMessage = document.getElementById('regMessage');
const openCameraBtn = document.getElementById('openCameraBtn');
const cameraModal = document.getElementById('cameraModal');
const cameraVideo = document.getElementById('cameraVideo');
const captureBtn = document.getElementById('captureBtn');
const closeCameraBtn = document.getElementById('closeCameraBtn');
const createClassBtn = document.getElementById('createClassBtn');
const createClassModal = document.getElementById('createClassModal');
const createClassForm = document.getElementById('createClassForm');
const cancelClassBtn = document.getElementById('cancelClassBtn');
const classesList = document.getElementById('classesList');
const attendanceClassSelect = document.getElementById('attendanceClassSelect');
const regClassSelect = document.getElementById('regClassSelect');

let selectedFile = null;
let attendanceData = null; // store backend response
let classes = []; // store classes list

function setMessage(text, type = 'info') {
    messageEl.textContent = text || '';
    messageEl.style.color = type === 'error' ? '#d23f44' : '#6b7280';
}

// Camera functions (open device camera, capture frame into the preview)
let _cameraStream = null;

async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setRegMessage('Camera not available on this device.', 'error');
        return;
    }

    try {
        _cameraStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
        if (cameraVideo) cameraVideo.srcObject = _cameraStream;
        if (cameraModal) cameraModal.classList.remove('hidden');
    } catch (err) {
        console.error('Camera start failed', err);
        setRegMessage('Unable to access camera. Check permissions.', 'error');
    }
}

function stopCamera() {
    if (_cameraStream) {
        _cameraStream.getTracks().forEach(t => t.stop());
        _cameraStream = null;
    }
    if (cameraVideo) cameraVideo.srcObject = null;
    if (cameraModal) cameraModal.classList.add('hidden');
}

function captureFromCamera() {
    if (!cameraVideo) return;
    const w = cameraVideo.videoWidth || 640;
    const h = cameraVideo.videoHeight || 480;
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(cameraVideo, 0, 0, w, h);
    canvas.toBlob((blob) => {
        if (!blob) { setRegMessage('Capture failed', 'error'); return; }
        let file;
        try { file = new File([blob], 'camera.jpg', { type: blob.type }); }
        catch (e) { file = blob; }
        handleFileSelection(file);
        stopCamera();
    }, 'image/jpeg', 0.92);
}

if (openCameraBtn) openCameraBtn.addEventListener('click', () => startCamera());
if (closeCameraBtn) closeCameraBtn.addEventListener('click', () => stopCamera());
if (captureBtn) captureBtn.addEventListener('click', () => captureFromCamera());


function setRegMessage(text, type = 'info') {
    if (!regMessage) return;
    regMessage.textContent = text || '';
    regMessage.style.color = type === 'error' ? '#d23f44' : '#6b7280';
}

function showOverlay(show) {
    overlay.classList.toggle('hidden', !show);
}

function resetPreview() {
    previewImage.src = '';
    previewContainer.classList.add('hidden');
    markBtn.disabled = true;
}

// When a file is selected (camera capture or uploaded)
function handleFileSelection(file) {
    if (!file) return resetPreview();
    selectedFile = file;
    const url = URL.createObjectURL(file);
    previewImage.src = url;
    previewContainer.classList.remove('hidden');
    markBtn.disabled = false;
    setMessage('Ready to analyze the photo.');
}

fileInput.addEventListener('change', e => {
    handleFileSelection(e.target.files && e.target.files[0]);
});
uploadInput.addEventListener('change', e => {
    handleFileSelection(e.target.files && e.target.files[0]);
});

// The camera label also triggers the hidden file input.
document.querySelector('label[for="uploadInput"]').addEventListener('click', () => {
    uploadInput.click();
});

// Mark Attendance -> send image to backend
markBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    setMessage('');
    attendanceSection.classList.add('hidden');
    showOverlay(true);

    try {
        const fd = new FormData();
        fd.append('image', selectedFile, selectedFile.name || 'photo.jpg');
        const classId = attendanceClassSelect.value;
        if (classId) {
            fd.append('class_id', classId);
        }

        const resp = await fetch('http://127.0.0.1:8000/attendance', {
            method: 'POST', body: fd
        });
        if (!resp.ok) {
            throw new Error(`Server returned ${resp.status}`);
        }
        const data = await resp.json();
        // expected: { date, present:[], absent:[], total }
        attendanceData = data;
        renderAttendance(data);
        setMessage('Review the detected students. Tap a student to toggle.');
    } catch (err) {
        console.error(err);
        setMessage('Could not process image. Please try again.', 'error');
    } finally {
        showOverlay(false);
    }
});

function clearLists() {
    presentList.innerHTML = '';
    absentList.innerHTML = '';
}

function makeStudentItem(id) {
    const li = document.createElement('li');
    li.tabIndex = 0;
    li.className = 'student-item';
    const span = document.createElement('span');
    span.className = 'name';
    span.textContent = id;
    li.appendChild(span);
    // toggle handler
    li.addEventListener('click', () => toggleStudent(id));
    li.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleStudent(id); } });
    return li;
}

function renderAttendance(data) {
    if (!data) return;
    clearLists();
    attDate.textContent = data.date || new Date().toISOString().slice(0, 10);
    attTotal.textContent = (data.total != null) ? data.total : '—';

    // Display class name if class_id is present
    if (data.class_id) {
        const classObj = classes.find(c => c.class_id === data.class_id);
        attClass.textContent = classObj ? `${classObj.name} (${data.class_id})` : data.class_id;
    } else {
        attClass.textContent = 'All Students';
    }

    // If backend found no faces, show friendly message
    const present = Array.isArray(data.present) ? data.present : [];
    const absent = Array.isArray(data.absent) ? data.absent : [];

    if (present.length === 0 && absent.length === 0) {
        setMessage('No faces detected in the photo. Try a clearer photo.', 'error');
        attendanceSection.classList.add('hidden');
        return;
    }

    present.forEach(sid => presentList.appendChild(makeStudentItem(sid)));
    absent.forEach(sid => absentList.appendChild(makeStudentItem(sid)));
    attendanceSection.classList.remove('hidden');
}

// Toggle a student between present and absent
function toggleStudent(id) {
    if (!attendanceData) return;
    const p = attendanceData.present || [];
    const a = attendanceData.absent || [];

    if (p.includes(id)) {
        // move to absent
        attendanceData.present = p.filter(x => x !== id);
        attendanceData.absent = [...a, id];
    } else if (a.includes(id)) {
        attendanceData.absent = a.filter(x => x !== id);
        attendanceData.present = [...p, id];
    }
    renderAttendance(attendanceData);
}

// Confirm & Save — sends final attendance to server (JSON)
confirmBtn.addEventListener('click', async () => {
    if (!attendanceData) return;
    showOverlay(true);
    setMessage('');
    const payload = {
        date: attendanceData.date || new Date().toISOString().slice(0, 10),
        present: attendanceData.present || [],
        absent: attendanceData.absent || [],
        total: attendanceData.total || (attendanceData.present.length + attendanceData.absent.length),
        class_id: attendanceData.class_id || attendanceClassSelect.value || null
    };

    try {
        // Attempt to POST final attendance. Endpoint may vary for your backend.
        const resp = await fetch('http://127.0.0.1:8000/attendance/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (resp.ok) {
            setMessage('Attendance successfully recorded.');
            // optionally collapse UI
            attendanceSection.classList.add('hidden');
            resetPreview();
        } else {
            // Friendly fallback message
            setMessage('Could not save to server. Please try again or contact support.', 'error');
        }
    } catch (err) {
        console.error(err);
        setMessage('Network error while saving. Please try again.', 'error');
    } finally {
        showOverlay(false);
    }
});

// Class Management Functions
async function loadClasses() {
    try {
        const resp = await fetch('http://127.0.0.1:8000/classes');
        if (resp.ok) {
            const data = await resp.json();
            classes = data.classes || [];
            renderClasses();
            updateClassSelects();
        }
    } catch (err) {
        console.error('Failed to load classes:', err);
    }
}

function renderClasses() {
    classesList.innerHTML = '';
    if (classes.length === 0) {
        classesList.innerHTML = '<p style="color: var(--muted);">No classes created yet. Create one to get started.</p>';
        return;
    }
    classes.forEach(cls => {
        const div = document.createElement('div');
        div.className = 'class-item';
        div.innerHTML = `
            <h4>${cls.name}</h4>
            <p>ID: ${cls.class_id}</p>
        `;
        div.addEventListener('click', () => {
            attendanceClassSelect.value = cls.class_id;
        });
        classesList.appendChild(div);
    });
}

function updateClassSelects() {
    // Update attendance class select
    attendanceClassSelect.innerHTML = '<option value="">All Students</option>';
    classes.forEach(cls => {
        const option = document.createElement('option');
        option.value = cls.class_id;
        option.textContent = `${cls.name} (${cls.class_id})`;
        attendanceClassSelect.appendChild(option);
    });

    // Update registration class select
    regClassSelect.innerHTML = '<option value="">Select a class</option>';
    classes.forEach(cls => {
        const option = document.createElement('option');
        option.value = cls.class_id;
        option.textContent = `${cls.name} (${cls.class_id})`;
        regClassSelect.appendChild(option);
    });
}

if (createClassBtn) {
    createClassBtn.addEventListener('click', () => {
        createClassModal.classList.remove('hidden');
    });
}

if (cancelClassBtn) {
    cancelClassBtn.addEventListener('click', () => {
        createClassModal.classList.add('hidden');
        createClassForm.reset();
    });
}

if (createClassForm) {
    createClassForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const classId = document.getElementById('newClassId').value.trim();
        const className = document.getElementById('newClassName').value.trim();

        if (!classId || !className) {
            alert('Please fill in all fields');
            return;
        }

        try {
            const resp = await fetch('http://127.0.0.1:8000/classes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ class_id: classId, name: className })
            });

            if (resp.ok) {
                createClassModal.classList.add('hidden');
                createClassForm.reset();
                await loadClasses();
            } else {
                const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
                alert(err.detail || 'Failed to create class');
            }
        } catch (err) {
            console.error(err);
            alert('Network error while creating class. Please try again.');
        }
    });
}

// Init
resetPreview();
setMessage('Use the camera or upload a photo to start.');
loadClasses();

// Registration form handler
if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const sid = regStudentId.value && regStudentId.value.trim();
        const file = regImage.files && regImage.files[0];
        if (!sid) { setRegMessage('Please enter a student id.', 'error'); return; }
        if (!file) { setRegMessage('Please select a photo.', 'error'); return; }

        setRegMessage('');
        showOverlay(true);
        regBtn.disabled = true;

        try {
            const fd = new FormData();
            fd.append('student_id', sid);
            fd.append('image', file, file.name || 'photo.jpg');

            const classId = document.getElementById('regClassSelect').value;
            const regNo = document.getElementById('regRegNo').value.trim();
            const program = document.getElementById('regProgram').value.trim();
            const semester = document.getElementById('regSemester').value.trim();

            if (classId) fd.append('class_id', classId);
            if (regNo) fd.append('reg_no', regNo);
            if (program) fd.append('program', program);
            if (semester) fd.append('semester', semester);

            const resp = await fetch('http://127.0.0.1:8000/register', {
                method: 'POST', body: fd
            });

            if (resp.ok) {
                const data = await resp.json();
                setRegMessage(`Registered ${data.student_id}`);
                // clear inputs
                registerForm.reset();
            } else {
                const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
                setRegMessage(err.detail || 'Registration failed', 'error');
            }
        } catch (err) {
            console.error(err);
            setRegMessage('Network error while registering. Please try again.', 'error');
        } finally {
            regBtn.disabled = false;
            showOverlay(false);
        }
    });
}
