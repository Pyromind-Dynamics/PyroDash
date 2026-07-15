from abc import ABC, abstractmethod
import random

import pandas
from datasets import load_dataset


class DatasetHandler(ABC):
    """Load benchmark questions/answers only. Scoring lives in boxed_socre."""

    def __init__(self, num_examples: int = None):
        self.num_examples = num_examples if num_examples is not None else 1

    @abstractmethod
    def load_data(self):
        """
        Load the dataset and return (questions, answers).

        questions: list[str]
        answers: list[str]
        """
        pass


class MathDatasetHandler(DatasetHandler):
    def load_data(self):
        df = pandas.read_csv(
            "https://openaipublic.blob.core.windows.net/simple-evals/math_500_test.csv"
        )
        examples = [row.to_dict() for _, row in df.iterrows()]
        questions = [example["Question"] for example in examples]
        answers = [example["Answer"] for example in examples]
        return questions, answers


class Gsm8kDatasetHandler(DatasetHandler):
    def load_data(self):
        dataset = load_dataset("openai/gsm8k", "main", split="test")
        examples = [row for row in dataset]
        questions = [example["question"] for example in examples]
        answers = [example["answer"].split("#### ")[-1] for example in examples]
        return questions, answers


class AmcDatasetHandler(DatasetHandler):
    def load_data(self):
        dataset = load_dataset("zwhe99/amc23", split="test")
        examples = [row for row in dataset]
        questions = [example["question"] for example in examples]
        answers = [example["answer"] for example in examples]
        return questions, answers


class MinervaDatasetHandler(DatasetHandler):
    def load_data(self):
        dataset = load_dataset("zwhe99/simplerl-minerva-math", split="test")
        examples = [row for row in dataset]
        questions = [example["problem"] for example in examples]
        answers = [example["answer"] for example in examples]
        return questions, answers


class OlympiadDatasetHandler(DatasetHandler):
    def load_data(self):
        dataset = load_dataset("zwhe99/simplerl-OlympiadBench", split="test")
        examples = [row for row in dataset]
        questions = [example["question"] for example in examples]
        answers = [example["final_answer"][0] for example in examples]
        return questions, answers


class Aime2024DatasetHandler(DatasetHandler):
    def load_data(self):
        dataset = load_dataset("HuggingFaceH4/aime_2024", split="train")
        examples = [row for row in dataset]
        questions = [example["problem"] for example in examples] * 32
        answers = [example["answer"] for example in examples] * 32
        return questions, answers


class Aime2025DatasetHandler(DatasetHandler):
    def load_data(self):
        dataset = load_dataset("yentinglin/aime_2025", "default")["train"]
        examples = [row for row in dataset]
        questions = [example["problem"] for example in examples] * 32
        answers = [example["answer"] for example in examples] * 32
        return questions, answers


class Mydataset_DatasetHandler(DatasetHandler):
    def __init__(self, name: str = "qwen3_frequent_solver_v1", num_examples: int = None):
        super().__init__(num_examples)
        self.name = name

    def load_data(self):
        dataset = load_dataset(self.name)["train"]
        examples = []

        for row in dataset:
            example = {
                "question": row["problem"],
                "answer": row["answer"],
            }
            examples.append(example)

        random.shuffle(examples)

        questions = []
        answers = []
        for example in examples:
            questions.append(example["question"])
            answers.append(example["answer"])
        return questions, answers


def get_dataset_handler(dataset_name: str, name: str = None) -> DatasetHandler:
    if dataset_name == "math":
        return MathDatasetHandler()
    if dataset_name == "gsm8k":
        return Gsm8kDatasetHandler()
    if dataset_name == "amc":
        return AmcDatasetHandler()
    if dataset_name == "minerva":
        return MinervaDatasetHandler()
    if dataset_name == "olympiad":
        return OlympiadDatasetHandler()
    if dataset_name == "aime2024":
        return Aime2024DatasetHandler()
    if dataset_name == "aime2025":
        return Aime2025DatasetHandler()
    if dataset_name == "mydataset":
        return Mydataset_DatasetHandler(name=name)
    raise ValueError(f"Dataset {dataset_name} not found")
