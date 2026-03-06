import json
import logging
from os import environ

from dotenv import load_dotenv
from databricks_langchain import ChatDatabricks
import pandas as pd

load_dotenv()
logger = logging.getLogger(__name__)
llm_endpoint = environ.get(
    "DATABRICKS_LLM_ENDPOINT", "databricks-qwen3-next-80b-a3b-instruct"
)


class LlmSummarizer:
    """LlmSummarizer: Generates concise summaries from datasets using a language model.

    This class provides a method to convert a pandas DataFrame into a textual summary
    and another method to generate a summary from structured data using a language model.
    """

    @staticmethod
    def dataframe_to_text(df: pd.DataFrame) -> str:
        """Convert a pandas DataFrame to a string representation without the index.

        Parameters:
        df (pd.DataFrame): The DataFrame to be converted.

        Returns:
        str: A string representation of the DataFrame, excluding the index.

        Example:
        >>> df = pd.DataFrame({'A': [1, 2], 'B': [3, 4]})
        >>> dataframe_to_text(df)
        'A    B\n--- ----\n1    3\n2    4
        """

        return df.to_string(index=False)

    def summarize(self, columns, data, question):
        """Summarizes the given dataset using a chat model.

        Args:
            columns (list of dict): List of column definitions.
            data (list): Data to be summarized.
            question (str): User query to guide the summary.

        Returns:
            str: A concise summary of the dataset based on the user query.
        """

        model = ChatDatabricks(endpoint=llm_endpoint, temperature=0.1)
        df = pd.DataFrame(data, columns=[col["name"] for col in columns])

        table_text = self.dataframe_to_text(df)

        prompt_template = """
            You are an expert data analyst. Below is a dataset.

            Your task is to analyze the data and provide a response formatted in Markdown for Microsoft Teams:
            - Use **Bold** for headers.
            - Use bullet points for lists.
            
            Provide:
            1. **Summary**: A concise, insightful summary (2-4 sentences) of the key trends or observations.
            2. **Next Best Action**: A recommendation based on the data.

            Dataset:
            {data}

            User Query:
            {query}
            """

        formatted_prompt = prompt_template.format(data=table_text, query=question)

        # Request completion
        response = model.invoke(formatted_prompt)

        if hasattr(response, "content"):
            response_content = response.content
        else:
            response_content = str(response)

        # The LLM may return a JSON string with reasoning and text parts.
        # We need to parse it and extract the user-facing text.
        try:
            parsed_response = json.loads(response_content)
            # The response is expected to be a list of dictionaries
            if isinstance(parsed_response, list):
                for item in parsed_response:
                    # We are interested in the part with type 'text'
                    if (
                        isinstance(item, dict)
                        and item.get("type") == "text"
                        and "text" in item
                    ):
                        return item["text"]
            # If the expected structure isn't found, return the raw content as a fallback.
            return response_content
        except (json.JSONDecodeError, TypeError):
            # If JSON parsing fails, assume it's the direct text response.
            return response_content
