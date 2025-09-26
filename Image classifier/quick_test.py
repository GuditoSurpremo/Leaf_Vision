import os
import io, base64
from transformers import AutoImageProcessor, AutoModelForImageClassification
from PIL import Image, ImageDraw
import torch

# Path where the model repo was downloaded by hf CLI
REPO_DIR = r"c:\Image classifier\models\crop_leaf_diseases_vit"
TEST_IMAGE = os.getenv("TEST_IMAGE", r"images.jpg")  # put a test image path here


def _ensure_test_image(path: str):
    """Create a simple synthetic leaf-like image if it doesn't exist."""
    if os.path.isfile(path):
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img = Image.new("RGB", (224, 224), (34, 139, 34))  # green background
    draw = ImageDraw.Draw(img)
    # draw simple veins
    draw.line((112, 10, 112, 214), fill=(200, 255, 200), width=3)
    for offset in range(-90, 100, 30):
        draw.line((112, 112, 200, 112 + offset), fill=(170, 230, 170), width=2)
        draw.line((112, 112, 24, 112 + offset), fill=(170, 230, 170), width=2)
    img.save(path, format="JPEG", quality=90)


def _show_matplotlib(img: Image.Image, top_items):
    """Display the input image and a horizontal bar chart of Top-K probs using matplotlib.
    Also saves a PNG next to the script.
    """
    try:
        import matplotlib.pyplot as plt
        labels = [lbl for (lbl, _p) in top_items][::-1]
        probs = [float(_p) for (_lbl, _p) in top_items][::-1]

        fig, (ax_img, ax_bar) = plt.subplots(
            1, 2, figsize=(8, 4), gridspec_kw={"width_ratios": [1, 1.2]}
        )
        ax_img.imshow(img)
        ax_img.set_title("Input")
        ax_img.axis("off")

        ax_bar.barh(labels, probs, color="#8b5cf6")
        ax_bar.set_xlim(0, 1)
        ax_bar.set_xlabel("Probability")
        ax_bar.set_title("Top predictions")

        plt.tight_layout()
        out_png = os.path.join(os.getcwd(), "prediction_plot.png")
        plt.savefig(out_png, dpi=150, bbox_inches="tight")
        print(f"Saved plot to: {out_png}")

        # Try to show the window (may require a GUI backend)
        try:
            plt.show()
        except Exception:
            pass
    except Exception as e:
        print(f"Matplotlib visualization skipped: {e}")


def main():
    if not os.path.isdir(REPO_DIR):
        raise SystemExit(f"Model repo not found at {REPO_DIR}. Run the download step first.")

    _ensure_test_image(TEST_IMAGE)

    processor = AutoImageProcessor.from_pretrained(REPO_DIR, use_fast=True)
    model = AutoModelForImageClassification.from_pretrained(REPO_DIR)
    model.eval()

    img = Image.open(TEST_IMAGE).convert("RGB")
    inputs = processor(images=img, return_tensors="pt")

    with torch.inference_mode():
        logits = model(**inputs).logits
        pred_id = int(logits.argmax(dim=-1).item())

    label = model.config.id2label.get(pred_id, str(pred_id))
    print(f"Prediction: {label} (class id: {pred_id})")

    # Also show a ranked probability list (Top-5) with simple bars and save an HTML report
    probs = torch.softmax(logits, dim=-1).squeeze(0)
    topk = min(5, probs.numel())
    values, indices = torch.topk(probs, k=topk)

    id2label = getattr(model.config, "id2label", {})
    top_items = [(id2label.get(int(i), str(int(i))), float(v)) for v, i in zip(values.tolist(), indices.tolist())]

    print("\nTop probabilities:")
    for lbl, p in top_items:
        bar = "█" * max(1, int(p * 40))
        print(f"{lbl:<30} {p:0.3f} {bar}")

    # Generate a lightweight HTML report similar to the shown visualization
    def _img_to_data_url(pil_img: Image.Image) -> str:
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    img_small = img.copy()
    img_small.thumbnail((256, 256))
    data_url = _img_to_data_url(img_small)

    bars_html = "\n".join(
        [
            f'<div class="row"><div class="label">{lbl}</div>'
            f'<div class="bar"><div class="fill" style="width:{int(p*100)}%"></div></div>'
            f'<div class="score">{p:.3f}</div></div>'
            for lbl, p in top_items
        ]
    )

    html = f"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Crop Disease Prediction</title>
<style>
  body {{ font-family: Segoe UI, Arial, sans-serif; margin: 24px; }}
  .container {{ max-width: 640px; margin: auto; }}
  .img {{ text-align: center; margin-bottom: 16px; }}
  .row {{ display: grid; grid-template-columns: 1fr 4fr 60px; align-items: center; gap: 8px; margin: 8px 0; }}
  .label {{ color: #444; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .bar {{ background:#eee; border-radius: 4px; height: 10px; position: relative; }}
  .fill {{ background: linear-gradient(90deg,#8b5cf6,#a78bfa); height:100%; border-radius: 4px; }}
  .score {{ text-align: right; color:#333; font-variant-numeric: tabular-nums; }}
  .footer {{ margin-top: 16px; color:#666; font-size: 12px; }}
</style>
</head>
<body>
  <div class="container">
    <div class="img"><img src="{data_url}" alt="input" style="max-height:256px; border-radius:8px;"/></div>
    {bars_html}
    <div class="footer">Top-{topk} predictions. Source image: {os.path.abspath(TEST_IMAGE)}</div>
  </div>
</body>
</html>
"""

    out_path = os.path.join(os.getcwd(), "prediction_report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nSaved visual report to: {out_path}")

    # Show with matplotlib as requested
    _show_matplotlib(img, top_items)


if __name__ == "__main__":
    main()
