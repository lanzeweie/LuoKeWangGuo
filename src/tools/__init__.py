"""模板工具"""
from src.tools.template_captor import TemplateCaptor, TemplateRegion
from src.tools.template_loader import TemplateLoader
from src.tools.relative_coordinate_picker import (
    RelativeCoordinatePicker,
    PickerMode,
    PointCoords,
    RectCoords,
)

__all__ = [
    "TemplateCaptor",
    "TemplateRegion",
    "TemplateLoader",
    "RelativeCoordinatePicker",
    "PickerMode",
    "PointCoords",
    "RectCoords",
]
