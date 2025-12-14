try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    class _CV2Stub:
        IMREAD_COLOR = 1

        def __getattr__(self, name):
            # Provide common attributes used in this repo to keep the editor happy.
            if name == 'imread':
                def _imread(*args, **kwargs):
                    raise ImportError("cv2.imread is not available because OpenCV is not installed")
                return _imread
            raise ImportError("cv2 is not available in the current environment")

    cv2 = _CV2Stub()
import os
import pickle
from face_engine import get_embeddings

BASE_DIR = "../students"
embeddings = []
student_ids = []

for student in os.listdir(BASE_DIR):
    folder = os.path.join(BASE_DIR, student)

    for img in os.listdir(folder):
        image = cv2.imread(os.path.join(folder, img))
        face_embs = get_embeddings(image)

        if face_embs:
            embeddings.append(face_embs[0])
            student_ids.append(student)

with open("encodings.pkl", "wb") as f:
    pickle.dump((embeddings, student_ids), f)

print("✅ Students registered")
