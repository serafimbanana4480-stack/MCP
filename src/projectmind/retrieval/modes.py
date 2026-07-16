from enum import Enum


class RetrievalMode(str, Enum):
    exploratory = "exploratory"
    surgical = "surgical"
    debug = "debug"
