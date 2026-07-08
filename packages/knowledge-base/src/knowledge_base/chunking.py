from langchain_text_splitters import CharacterTextSplitter


# https://docs.langchain.com/oss/python/integrations/splitters/character_text_splitter
def fixed_size_chunking(text: str):
    splitter = CharacterTextSplitter(chunk_size=50, chunk_overlap=10)
    chunks = splitter.split_text(text)
    return chunks
