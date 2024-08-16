from concurrent import futures
import logging

import grpc
import text_analyzer_pb2
import text_analyzer_pb2_grpc
import text_reader_pb2
import text_reader_pb2_grpc

from collections import defaultdict
from utils import constants

logging.basicConfig(level=logging.INFO)


class TextAnalyzerService(text_analyzer_pb2_grpc.TextAnalysisServicer):
    def __init__(self, archaic_words, text_reader_address):
        self.archaic_words = set(word.lower() for word in archaic_words)
        self.word_count = 0
        self.total_word_length = 0
        self.sentence_count = 0
        self.total_sentence_length = 0
        self.archaic_word_count = defaultdict(int)
        self.current_sentence = []
        self.text_reader_address = text_reader_address
        self.start_processing()

    def start_processing(self):
        def process_words():
            with grpc.insecure_channel(self.text_reader_address) as channel:
                stub = text_reader_pb2_grpc.TextReaderStub(channel)
                try:
                    response = stub.GetNextWord(text_reader_pb2.WordRequest())
                    while not response.eof:
                        self.analyze_word(response.word)
                        response = stub.GetNextWord(text_reader_pb2.WordRequest())
                except grpc.RpcError as e:
                    logging.error(f"RPC error: {e}")

        # Start processing in a separate thread
        import threading

        threading.Thread(target=process_words, daemon=True).start()

    def analyze_word(self, word):
        word = word.strip()
        self.word_count += 1
        self.total_word_length += len(word)
        self.current_sentence.append(word)

        if word.lower() in self.archaic_words:
            self.archaic_word_count[word.lower()] += 1

        if word.endswith((".", "!", "?")):
            self.sentence_count += 1
            self.total_sentence_length += len(self.current_sentence)
            self.current_sentence = []

        logging.info(f"Analyzed word: {word}")

    def GetAnalysis(self, request, context):
        avg_word_length = (
            self.total_word_length / self.word_count if self.word_count > 0 else 0
        )
        avg_sentence_length = (
            self.total_sentence_length / self.sentence_count
            if self.sentence_count > 0
            else 0
        )

        return text_analyzer_pb2.AnalysisResponse(
            avg_word_length=avg_word_length,
            avg_sentence_length=avg_sentence_length,
            archaic_word_counts={
                word: count for word, count in self.archaic_word_count.items()
            },
        )


def serve():
    archaic_words = set()
    with open("data/archaic_words.txt", "r", encoding="utf-8") as f:
        archaic_words = f.read().splitlines()

    text_reader_address = constants.TEXT_READER_BASE_URL
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    text_analyzer_pb2_grpc.add_TextAnalysisServicer_to_server(
        TextAnalyzerService(archaic_words, text_reader_address), server
    )

    logging.info("Starting server on port %s", constants.PORT)

    server.add_insecure_port(f"[::]:{constants.PORT}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
