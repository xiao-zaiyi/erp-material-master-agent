from sources.ncc import NccMaterialSource


def create_material_source(settings):
    source_type = settings.source_type.strip().lower()
    if not settings.source_url:
        raise RuntimeError("缺少 MATERIAL_SOURCE_URL 配置")
    if source_type == "ncc":
        return NccMaterialSource.from_url(settings.source_url)
    raise ValueError(f"不支持的物料数据源：{settings.source_type}")
