from docling.document_converter import DocumentConverter

# Prefetch che potrebbe essere usato durante la creazione della base di conoscenza?
# docling.utils.model_downloader.download_models()

def convert(source: str):
    """
    source: il path al file da convertire.
    """

    converter = DocumentConverter()
    doc = converter.convert(source).document
    return doc.export_to_markdown()
