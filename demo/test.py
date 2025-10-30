import os
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv("../.env")

client = OpenAI(
  base_url = os.getenv("AZURE_OPENAI_ENDPOINT")+"/openai/v1/",  
  api_key=os.getenv("AZURE_OPENAI_API_KEY")  
)

class CalendarEvent(BaseModel):
    name: str
    date: str
    participants: list[str]

completion = client.responses.parse(
    model="gpt-5-mini", # replace with the model deployment name of your gpt-5-nanoo 2024-08-06 deployment
    input=[
        {"role": "system", "content": "Extract the event information."},
        {"role": "user", "content": "Alice and Bob are going to a science fair on Friday."},
    ],
    text_format=CalendarEvent,
)

event = completion.output_parsed

print(event)
print(completion.model_dump_json(indent=2))