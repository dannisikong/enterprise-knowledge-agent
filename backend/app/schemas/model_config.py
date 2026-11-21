from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    api_key: str = Field(min_length=8, max_length=512)
    base_url: str = Field(default="https://api.openai.com/v1", min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=128)


class ModelTestResponse(BaseModel):
    ok: bool
    message: str
