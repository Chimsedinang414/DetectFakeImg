# DetectFakeIMG Backend
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass
