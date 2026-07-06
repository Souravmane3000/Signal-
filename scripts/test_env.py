from dotenv import load_dotenv
import os

load_dotenv()

print("OPENAI:", bool(os.getenv("OPENAI_API_KEY")))
print("TAVILY:", bool(os.getenv("TAVILY_API_KEY")))
print("LANGSMITH:", bool(os.getenv("LANGSMITH_API_KEY")))