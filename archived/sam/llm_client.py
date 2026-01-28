"""
SAM LLM Client

Azure OpenAI client wrapper for SAM operations.
Provides unified interface for chat completions and embeddings.
"""

import os
from typing import Optional, List, Dict, Any, Type, TypeVar
from pydantic import BaseModel
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

T = TypeVar('T', bound=BaseModel)


class LLMClient:
    """
    LLM Client for SAM operations.
    
    Wraps Azure OpenAI for:
    - Chat completions (with structured output support)
    - Embeddings generation
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        reasoning_model: Optional[str] = None,
        processing_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        client: Optional[AzureOpenAI] = None
    ):
        """
        Initialize LLM client.
        
        Args:
            api_key: Azure OpenAI API key (or from AZURE_OPENAI_API_KEY env)
            endpoint: Azure OpenAI endpoint (or from AZURE_OPENAI_ENDPOINT env)
            api_version: API version (or from AZURE_OPENAI_API_VERSION env)
            reasoning_model: Model for complex reasoning tasks
            processing_model: Model for fast processing tasks
            embedding_model: Model for embeddings
            client: Optional pre-configured AzureOpenAI client
        """
        if client:
            self._client = client
            self._own_client = False
        else:
            # Get from environment
            api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
            endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
            api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
            
            if not api_key or not endpoint:
                raise ValueError(
                    "Must provide client or set AZURE_OPENAI_API_KEY and "
                    "AZURE_OPENAI_ENDPOINT environment variables."
                )
            
            self._client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=api_version
            )
            self._own_client = True
        
        # Model deployments
        self.reasoning_model = reasoning_model or os.getenv(
            "AZURE_OPENAI_REASONING_MODEL", "gpt-4o"
        )
        self.processing_model = processing_model or os.getenv(
            "AZURE_OPENAI_PROCESSING_MODEL", "gpt-4o-mini"
        )
        self.embedding_model = embedding_model or os.getenv(
            "AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-ada-002"
        )
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Generate a chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (defaults to processing_model)
            temperature: Sampling temperature (not supported by o-series models)
            max_tokens: Maximum tokens in response
            **kwargs: Additional arguments for the API
            
        Returns:
            Response content as string
        """
        model = model or self.processing_model
        
        # Build API call params - only include temperature if set and not an o-series model
        api_kwargs = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        if max_tokens is not None:
            api_kwargs["max_tokens"] = max_tokens
        
        # O-series models don't support temperature
        if temperature is not None and not self._is_o_series(model):
            api_kwargs["temperature"] = temperature
        
        response = self._client.chat.completions.create(**api_kwargs)
        
        return response.choices[0].message.content
    
    def _is_o_series(self, model: str) -> bool:
        """Check if model is an o-series (reasoning) model that doesn't support temperature."""
        o_series_patterns = ["o1", "o3", "o4", "gpt-5", "o1-mini", "o1-preview"]
        model_lower = model.lower()
        return any(pattern in model_lower for pattern in o_series_patterns)
    
    def chat_completion_structured(
        self,
        messages: List[Dict[str, str]],
        response_format: Type[T],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> T:
        """
        Generate a chat completion with structured output.
        
        Uses Pydantic model for response parsing.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            response_format: Pydantic model class for structured output
            model: Model to use (defaults to processing_model)
            temperature: Sampling temperature (not supported by o-series models)
            **kwargs: Additional arguments for the API
            
        Returns:
            Parsed response as Pydantic model instance
        """
        model = model or self.processing_model
        
        # Build API call params
        api_kwargs = {
            "model": model,
            "messages": messages,
            "response_format": response_format,
            **kwargs
        }
        
        # O-series models don't support temperature
        if temperature is not None and not self._is_o_series(model):
            api_kwargs["temperature"] = temperature
        
        response = self._client.beta.chat.completions.parse(**api_kwargs)
        
        return response.choices[0].message.parsed
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (1536 dimensions for ada-002)
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        response = self._client.embeddings.create(
            input=text,
            model=self.embedding_model
        )
        
        return response.data[0].embedding
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Filter empty strings
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return []
        
        response = self._client.embeddings.create(
            input=valid_texts,
            model=self.embedding_model
        )
        
        return [data.embedding for data in response.data]
    
    def complete_json(
        self,
        prompt: str,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a JSON response from a prompt.
        
        Useful for LLM-as-judge and evaluation tasks.
        
        Args:
            prompt: The prompt to send
            model: Model to use (defaults to processing_model)
            
        Returns:
            Parsed JSON dictionary
        """
        import json
        import re
        
        model = model or self.processing_model
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant. Always respond with valid JSON."},
            {"role": "user", "content": prompt}
        ]
        
        response = self.chat_completion(messages, model=model)
        
        # Try to extract JSON from response
        try:
            # First try direct parsing
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON in markdown code blocks
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
            if json_match:
                return json.loads(json_match.group(1))
            
            # Try to find JSON object directly
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group(0))
            
            # Fallback
            return {"raw_response": response}
    
    def close(self):
        """Close the client if we own it."""
        if self._own_client and hasattr(self._client, 'close'):
            self._client.close()
