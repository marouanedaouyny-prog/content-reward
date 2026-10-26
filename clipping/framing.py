"""Speaker-focus framing from local face detection with an honest fit fallback.

Faces are detected with OpenCV's bundled Haar cascade on sampled frames. A
crop is produced only when the dominant face is present in most sampled frames
and stays spatially stable (PRD-GROWTH section 12: speaker-focus when reliable,
otherwise fit). The crop itself is static for the whole window, so the export
never gains shaky camera movement (section 13). Every report records what was
actually observed; no speaker identity or attention is inferred.
"""

import math

# Reliability gates for a static speaker crop.
MIN_COVERAGE = 0.5      # Fraction of sampled frames that must contain a face.
MAX_CENTER_SPREAD = 0.12  # Dominant-face center stability as frame fraction.
FACE_HEIGHT_RANGE = (0.08, 0.45)  # Face must fit a portrait crop comfortably.
ANALYSIS_WIDTH = 480    # Frames are downscaled before detection for speed.
ASPECT_RATIOS = {'9:16': 9 / 16, '16:9': 16 / 9, '1:1': 1.0}

def _cascade_unavailable() -> bool:
    """Check if OpenCV CascadeClassifier is available."""
    try:
        import cv2
        from cv2 import CascadeClassifier
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        cascade = CascadeClassifier(cascade_path)
        return cascade.empty()
    except (ImportError, AttributeError):
        return True


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def crop_rect(frame_width, frame_height, centers, face_heights, aspect_ratio):
    """Pure crop math: stable face statistics to a clamped, even crop rect.

    Returns ``(rect_or_none, reason)``. Rects are ``(x, y, width, height)``
    integers in source-frame pixels, aligned to even numbers for libx264.
    """
    if (not centers or len(centers) != len(face_heights) or frame_width <= 0 or frame_height <= 0
            or aspect_ratio not in ASPECT_RATIOS):
        return None, 'no_face_evidence'
    center_x, center_y = _median([c[0] for c in centers]), _median([c[1] for c in centers])
    spread = max(_median([abs(c[0] - center_x) for c in centers]),
                 _median([abs(c[1] - center_y) for c in centers]))
    face_height = _median(face_heights)
    if spread > MAX_CENTER_SPREAD:
        return None, 'face_center_too_unstable'
    if not FACE_HEIGHT_RANGE[0] <= face_height <= FACE_HEIGHT_RANGE[1]:
        return None, 'face_size_outside_crop_range'
    ratio = ASPECT_RATIOS[aspect_ratio]
    crop_height = min(frame_height, max(face_height * frame_height * 3.2, frame_height * 0.55))
    crop_width = crop_height * ratio
    if crop_width > frame_width:
        crop_width, crop_height = frame_width, frame_width / ratio
    crop_width = min(crop_width, frame_width)
    crop_height = min(crop_height, frame_height)
    x = min(max(center_x * frame_width - crop_width / 2, 0), frame_width - crop_width)
    y = min(max(center_y * frame_height - crop_height / 2, 0), frame_height - crop_height)
    even = lambda value: max(2, int(round(value / 2)) * 2)
    x, y = even(x), even(y)
    width = min(even(crop_width), frame_width - x)
    height = min(even(crop_height), frame_height - y)
    face_pixels = face_height * frame_height
    vertical = center_y * frame_height - y
    if not face_pixels * 0.6 <= vertical <= height - face_pixels * 0.6:
        return None, 'face_needs_headroom_outside_frame'
    return (x, y, width, height), 'stable_face_crop'


def analyze(source_path, start, duration, aspect_ratio='9:16'):
    """Sample one clip window and report a reliable speaker crop, if any."""
    report = {'crop': None, 'reason': None, 'frames_sampled': 0, 'frames_with_face': 0,
              'face_coverage': 0.0, 'basis': 'OpenCV Haar face detection on sampled frames; '
                                             'no speaker identity or attention is inferred.'}
    if _cascade_unavailable():
        return {**report, 'reason': 'opencv_unavailable'}
    import cv2
    from cv2 import CascadeClassifier
    if aspect_ratio not in ASPECT_RATIOS:
        return {**report, 'reason': 'unsupported_aspect_ratio'}
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
           for value in (start, duration)) or start < 0 or duration <= 0:
        return {**report, 'reason': 'invalid_window'}
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        return {**report, 'reason': 'source_unreadable'}
    try:
        frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        cascade = CascadeClassifier(cascade_path)
        if cascade.empty():
            return {**report, 'reason': 'detector_unavailable'}
        samples = max(12, min(60, int(duration * 2)))
        centers, face_heights, decoded = [], [], 0
        for index in range(samples):
            capture.set(cv2.CAP_PROP_POS_MSEC, (start + duration * (index + .5) / samples) * 1000)
            ok, frame = capture.read()
            if not ok:
                continue
            decoded += 1
            scale = ANALYSIS_WIDTH / frame.shape[1]
            small = cv2.resize(frame, (ANALYSIS_WIDTH, max(2, int(frame.shape[0] * scale))))
            faces = cascade.detectMultiScale(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY),
                                             scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
            if len(faces) == 0:
                continue
            x, y, face_w, face_h = max(faces, key=lambda face: face[2] * face[3])
            centers.append(((x + face_w / 2) / small.shape[1], (y + face_h / 2) / small.shape[0]))
            face_heights.append(face_h / small.shape[0])
        coverage = len(centers) / decoded if decoded else 0.0
        base = {**report, 'frames_sampled': decoded, 'frames_with_face': len(centers),
                'face_coverage': round(coverage, 3)}
        if not decoded:
            return {**base, 'reason': 'no_frames_decoded'}
        if coverage < MIN_COVERAGE:
            return {**base, 'reason': 'no_stable_face_detected'}
        rect, reason = crop_rect(frame_width, frame_height, centers, face_heights, aspect_ratio)
        return {**base, 'crop': list(rect) if rect else None, 'reason': reason}
    finally:
        capture.release()
