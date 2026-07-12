import logging


def setup(log_file: str):
    """
    Setup logging.
    """
    logging.basicConfig(level=logging.INFO, filename=log_file, filemode="w",
                        format="%(asctime)s - %(levelname)s - %(message)s", force=True)

    # Disabilita logging di Langchain
    # https://github.com/langchain-ai/langchain/issues/14065
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
