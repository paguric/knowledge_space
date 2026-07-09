from langchain_text_splitters import CharacterTextSplitter


# https://docs.langchain.com/oss/python/integrations/splitters/character_text_splitter
def fixed_size_chunking(text: str):
    splitter = CharacterTextSplitter(
        separator="\n\n",
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        is_separator_regex=False,
    )

    chunks = splitter.split_text(text)
    return chunks
