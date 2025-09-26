import os
from typing import Optional
from PIL import Image
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

# Lazy HF imports to keep server responsive if deps missing
_processor = None
_model = None
_label2id = None
_id2label = None

# Paths to model assets (relative to workspace root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(os.path.dirname(BASE_DIR), 'Image classifier', 'models', 'crop_leaf_diseases_vit')


def _load_model_if_needed() -> Optional[str]:
    global _processor, _model, _label2id, _id2label
    if _model is not None and _processor is not None:
        return None
    try:
        # Explicit checks to produce clearer errors when assets are missing
        if not os.path.isdir(MODEL_DIR):
            return f"Model directory not found: {MODEL_DIR}"
        expected = [
            os.path.join(MODEL_DIR, 'config.json'),
            os.path.join(MODEL_DIR, 'preprocessor_config.json'),
        ]
        missing = [p for p in expected if not os.path.exists(p)]
        if missing:
            return f"Missing model files: {', '.join(os.path.basename(m) for m in missing)} in {MODEL_DIR}"

        from transformers import AutoImageProcessor, AutoModelForImageClassification
        _processor = AutoImageProcessor.from_pretrained(MODEL_DIR, local_files_only=True)
        _model = AutoModelForImageClassification.from_pretrained(MODEL_DIR, local_files_only=True)
        _model.eval()
        _label2id = getattr(_model.config, 'label2id', None)
        _id2label = getattr(_model.config, 'id2label', None)
        return None
    except Exception as e:
        return str(e)


def _predict_image(img: Image.Image):
    from torch import nn
    import torch

    # Ensure loaded
    err = _load_model_if_needed()
    if err:
        raise RuntimeError(f"Model load failed: {err}. Ensure 'transformers', 'torch', and 'safetensors' are installed and the model files exist in: {MODEL_DIR}")

    inputs = _processor(images=img, return_tensors='pt')
    with torch.no_grad():
        outputs = _model(**inputs)
        logits = outputs.logits
        probs = nn.functional.softmax(logits, dim=-1)[0]
        conf, idx = torch.max(probs, dim=-1)
        confidence = float(conf.item())
        label_idx = int(idx.item())

    if _id2label and label_idx in _id2label:
        label = _id2label[label_idx]
    elif _model and hasattr(_model.config, 'id2label') and label_idx in _model.config.id2label:
        label = _model.config.id2label[label_idx]
    else:
        label = f'class_{label_idx}'

    # Also return top-3 for UI if desired
    topk = min(3, probs.shape[-1])
    top_vals, top_idxs = torch.topk(probs, k=topk)
    top = [
        {
            'label': (_id2label.get(int(i), f'class_{int(i)}') if _id2label else f'class_{int(i)}'),
            'confidence': float(v.item()),
        }
        for v, i in zip(top_vals, top_idxs)
    ]

    return label, confidence, top


@api_view(['POST'])
def predict(request):
    try:
        if 'image' not in request.FILES:
            return Response({"error": "No image uploaded with key 'image'"}, status=status.HTTP_400_BAD_REQUEST)

        image_file = request.FILES['image']
        img = Image.open(image_file).convert('RGB')

        label, confidence, top = _predict_image(img)
        return Response({
            'label': label,
            'confidence': round(confidence, 4),
            'top': [{ 'label': t['label'], 'confidence': round(t['confidence'], 4)} for t in top],
        })
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
