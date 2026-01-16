"""
Image utilities for handling image encoding, decoding, and compression.

This module provides functionality for:
- Converting PIL Images to base64 strings
- Converting base64 strings back to PIL Images
- Intelligent image compression to stay under API size limits
"""

import base64
import io
from PIL import Image


def encode_image_to_base64(
    image: Image.Image, format: str = "JPEG", quality: int = 85
) -> str:
    """
    Convert a PIL Image to a base64-encoded string.

    Args:
        image: PIL Image object to encode
        format: Image format (default JPEG for compression)
        quality: JPEG quality 1-95 (default 85)

    Returns:
        Base64-encoded string representation of the image
    """
    buffered = io.BytesIO()

    if format.upper() == "JPEG":
        image.save(buffered, format=format, quality=quality, optimize=True)
    else:
        image.save(buffered, format=format)

    img_bytes = buffered.getvalue()
    size_mb = len(img_bytes) / (1024 * 1024)
    print(f"[Encoding] Format={format}, Quality={quality}, Size={size_mb:.2f} MB")

    return base64.b64encode(img_bytes).decode("utf-8")


def decode_base64_to_image(b64_string: str) -> Image.Image:
    """
    Convert a base64-encoded string back to a PIL Image.

    Args:
        b64_string: Base64-encoded image string.

    Returns:
        PIL Image object.
    """
    img_data = base64.b64decode(b64_string)
    return Image.open(io.BytesIO(img_data))


def compress_image_with_bytes(
    image: Image.Image, max_size_mb: float = 4.0, target_format: str = "JPEG"
) -> tuple[Image.Image, bytes]:
    """
    Compress an image and return both the PIL Image and compressed bytes.

    This ensures the bytes and image are perfectly synchronized - no re-encoding.

    Args:
        image: PIL Image to compress
        max_size_mb: Maximum size in MB (default 4.0 MB for safety margin)
        target_format: Output format (default JPEG for best compression)

    Returns:
        Tuple of (compressed PIL Image, compressed bytes)
    """
    max_size_bytes = int(max_size_mb * 1024 * 1024)
    original_size = (image.width, image.height)

    # Always convert to RGB for consistent compression
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    print(
        f"[Compression] Original: {original_size[0]}x{original_size[1]}, mode: {image.mode}"
    )

    # For very small targets (< 1 MB), start with dimension reduction immediately
    # This is because PIL Images will be re-encoded by smolagents
    if max_size_mb < 1.0:
        print(
            f"[Compression] Small target ({max_size_mb} MB), starting with dimension reduction"
        )
        # Try progressively smaller sizes - be very aggressive for tiny targets
        for scale in [0.5, 0.45, 0.4, 0.35, 0.3, 0.28, 0.25, 0.22, 0.2, 0.18, 0.15]:
            new_size = (int(image.width * scale), int(image.height * scale))
            resized = image.resize(new_size, Image.Resampling.LANCZOS)

            for quality in [85, 70, 55, 40, 30]:
                buffer = io.BytesIO()
                resized.save(
                    buffer, format=target_format, quality=quality, optimize=True
                )
                compressed_bytes = buffer.getvalue()
                size_mb = len(compressed_bytes) / (1024 * 1024)

                if len(compressed_bytes) <= max_size_bytes:
                    print(
                        f"[Compression] Success at scale={scale:.2f}, quality={quality}: "
                        f"{new_size[0]}x{new_size[1]}, {size_mb:.2f} MB"
                    )
                    buffer.seek(0)
                    compressed_image = Image.open(buffer)
                    return compressed_image, compressed_bytes

    # Standard approach for larger targets: try quality reduction first
    for quality in [95, 85, 75, 65, 55, 45, 35]:
        buffer = io.BytesIO()
        image.save(buffer, format=target_format, quality=quality, optimize=True)
        compressed_bytes = buffer.getvalue()
        size_mb = len(compressed_bytes) / (1024 * 1024)

        if len(compressed_bytes) <= max_size_bytes:
            print(f"[Compression] Success at quality={quality}: {size_mb:.2f} MB")
            buffer.seek(0)
            compressed_image = Image.open(buffer)
            return compressed_image, compressed_bytes

    # If quality reduction isn't enough, scale down dimensions
    print("[Compression] Quality reduction insufficient, trying dimension scaling...")
    scale_factors = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]

    for scale in scale_factors:
        new_size = (int(image.width * scale), int(image.height * scale))
        resized = image.resize(new_size, Image.Resampling.LANCZOS)

        # Try with moderate quality after resizing
        for quality in [85, 70, 55, 40]:
            buffer = io.BytesIO()
            resized.save(buffer, format=target_format, quality=quality, optimize=True)
            compressed_bytes = buffer.getvalue()
            size_mb = len(compressed_bytes) / (1024 * 1024)

            if len(compressed_bytes) <= max_size_bytes:
                print(
                    f"[Compression] Success at scale={scale:.1f}, quality={quality}: "
                    f"{new_size[0]}x{new_size[1]}, {size_mb:.2f} MB"
                )
                buffer.seek(0)
                compressed_image = Image.open(buffer)
                return compressed_image, compressed_bytes

    # Last resort: very small size with low quality
    print("[Compression] Using last resort: 30% scale, quality=30")
    final_size = (int(image.width * 0.3), int(image.height * 0.3))
    final_image = image.resize(final_size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    final_image.save(buffer, format=target_format, quality=30, optimize=True)
    compressed_bytes = buffer.getvalue()
    size_mb = len(compressed_bytes) / (1024 * 1024)
    print(f"[Compression] Final: {final_size[0]}x{final_size[1]}, {size_mb:.2f} MB")
    buffer.seek(0)
    compressed_image = Image.open(buffer)
    return compressed_image, compressed_bytes


def get_image_size_mb(
    image: Image.Image, format: str = "JPEG", quality: int = 85
) -> float:
    """
    Calculate the encoded size of an image in megabytes.

    Args:
        image: PIL Image to measure
        format: Encoding format (default JPEG)
        quality: JPEG quality (default 85)

    Returns:
        Size in megabytes
    """
    buffer = io.BytesIO()
    image.save(buffer, format=format, quality=quality, optimize=True)
    return buffer.tell() / (1024 * 1024)
