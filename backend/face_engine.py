try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    class _CV2Stub:
        def __getattr__(self, name):
            raise ImportError("cv2 is not available in the current environment")

    cv2 = _CV2Stub()

import numpy as np
try:
    from insightface.app import FaceAnalysis  # type: ignore
except Exception:  # pragma: no cover
    # Provide a helpful error at runtime; editor will not mark this import as unresolved.
    class FaceAnalysis:
        def __init__(self, *a, **kw):
            raise ImportError("insightface is not available in the current environment")

app = FaceAnalysis(name="buffalo_l")
app.prepare(ctx_id=0, det_size=(640, 640))

def get_embeddings(image):
    faces = app.get(image)
    embeddings = []

    for face in faces:
        embeddings.append(face.embedding)

    return embeddings
def recognize_faces(image, known_embeddings, known_ids, threshold=0.35):
    faces = app.get(image)
    present = set()

    for face in faces:
        emb = face.embedding
        sims = [np.dot(emb, k) / (np.linalg.norm(emb)*np.linalg.norm(k))
                for k in known_embeddings]

        best = np.argmax(sims)

        if sims[best] > (1 - threshold):
            present.add(known_ids[best])

    return present
