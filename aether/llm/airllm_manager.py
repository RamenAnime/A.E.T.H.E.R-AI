"""Quantized LLM loading (optional AirLLM) with Ollama fallback."""

from __future__ import annotations

import gc
import os
import time
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    import torch
except ImportError:
    torch = None  # type: ignore[assignment]


class QuantizationLevel(Enum):
    NONE = "none"
    INT8 = "int8"
    INT4 = "int4"
    INT2 = "int2"


class AirLLMManager:
    def __init__(self, cache_dir: str = "./models"):
        self.cache_dir = cache_dir
        self.loaded_models: Dict[str, Any] = {}
        self.model_configs: Dict[str, Dict] = {}
        os.makedirs(cache_dir, exist_ok=True)
        self.airllm_available = self._check_airllm()
        self.default_quantization = QuantizationLevel.INT4
        self.memory_estimates = {
            "llama3.1:8b": {"none": 4.9, "int8": 2.5, "int4": 1.2, "int2": 0.6},
            "llama3.1:70b": {"none": 40.0, "int8": 20.0, "int4": 10.0, "int2": 5.0},
            "codellama:7b": {"none": 3.8, "int8": 1.9, "int4": 0.95, "int2": 0.48},
            "mistral:7b": {"none": 4.1, "int8": 2.1, "int4": 1.0, "int2": 0.5},
        }

    def _check_airllm(self) -> bool:
        try:
            from airllm import AirLLMLlama2  # noqa: F401

            return True
        except ImportError:
            return False

    def load_model(
        self, model_name: str, quantization: Optional[QuantizationLevel] = None
    ) -> Any:
        quant = quantization or self.default_quantization
        cache_key = f"{model_name}_{quant.value}"
        if cache_key in self.loaded_models:
            return self.loaded_models[cache_key]
        if not self.airllm_available:
            return self._load_standard(model_name)
        try:
            from airllm import AirLLMLlama2

            compression = self._map_quantization(quant)
            model = AirLLMLlama2(
                pretrained_model_name_or_path=model_name,
                compression=compression,
                layer_sharing=True,
                cache_dir=self.cache_dir,
            )
            self.loaded_models[cache_key] = model
            self.model_configs[cache_key] = {
                "name": model_name,
                "quantization": quant.value,
                "loaded_at": time.time(),
            }
            self._report_memory_savings(model_name, quant)
            return model
        except Exception as exc:
            print(f"AirLLM load failed: {exc}. Using standard loading.")
            return self._load_standard(model_name)

    def _load_standard(self, model_name: str) -> Dict[str, Any]:
        if torch is None:
            raise ImportError("Install torch: pip install aether[llm]")
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=self.cache_dir)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            device_map="auto",
            cache_dir=self.cache_dir,
        )
        cache_key = f"{model_name}_none"
        bundle = {"model": model, "tokenizer": tokenizer}
        self.loaded_models[cache_key] = bundle
        return bundle

    def _map_quantization(self, quant: QuantizationLevel) -> str:
        mapping = {
            QuantizationLevel.INT8: "8bit",
            QuantizationLevel.INT4: "4bit",
            QuantizationLevel.INT2: "2bit",
        }
        return mapping.get(quant, "4bit")

    def _report_memory_savings(self, model_name: str, quant: QuantizationLevel) -> None:
        for key, estimates in self.memory_estimates.items():
            if key in model_name.lower():
                original = estimates["none"]
                quantized = estimates.get(quant.value, original)
                savings = ((original - quantized) / original) * 100 if original else 0
                print(f"  Memory: {original:.1f}GB -> {quantized:.1f}GB ({savings:.0f}% saved)")
                return

    def generate(
        self, model: Any, prompt: str, max_length: int = 512, temperature: float = 0.7
    ) -> str:
        if isinstance(model, dict) and "tokenizer" in model:
            inputs = model["tokenizer"](prompt, return_tensors="pt").to(model["model"].device)
            outputs = model["model"].generate(
                **inputs, max_new_tokens=max_length, temperature=temperature, do_sample=True
            )
            return model["tokenizer"].decode(outputs[0], skip_special_tokens=True)
        if not self.airllm_available:
            return "[Model not loaded]"
        try:
            input_tokens = model.tokenizer(
                prompt, return_tensors="pt", return_attention_mask=False
            )
            device = "cuda" if torch is not None and torch.cuda.is_available() else "cpu"
            ids = input_tokens["input_ids"].to(device)
            generation_output = model.generate(
                ids, max_new_tokens=max_length, use_cache=True, temperature=temperature
            )
            return model.tokenizer.decode(generation_output[0])
        except Exception as exc:
            return f"[Generation failed: {exc}]"

    def unload_model(self, model_name: str, quantization: Optional[QuantizationLevel] = None) -> None:
        quant = quantization or self.default_quantization
        cache_key = f"{model_name}_{quant.value}"
        self.loaded_models.pop(cache_key, None)
        self.model_configs.pop(cache_key, None)
        gc.collect()
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def get_memory_status(self) -> Dict[str, Any]:
        import psutil

        mem = psutil.virtual_memory()
        loaded_memory = 0.0
        for config in self.model_configs.values():
            for model_key, estimates in self.memory_estimates.items():
                if model_key in config["name"].lower():
                    loaded_memory += estimates.get(config["quantization"], 0)
                    break
        return {
            "total_ram_gb": mem.total / 1e9,
            "available_ram_gb": mem.available / 1e9,
            "used_ram_gb": mem.used / 1e9,
            "ram_percent": mem.percent,
            "loaded_models": len(self.loaded_models),
            "estimated_model_memory_gb": loaded_memory,
            "airllm_available": self.airllm_available,
        }


class OllamaAirLLMBridge:
    def __init__(self, use_airllm: bool = True, default_quantization: str = "int4"):
        self.use_airllm = use_airllm
        self.default_quantization = default_quantization
        self.airllm_manager = AirLLMManager() if use_airllm else None

    async def chat(
        self, model_name: str, messages: List[Dict[str, str]], use_quantization: Optional[bool] = None
    ) -> str:
        use_quant = use_quantization if use_quantization is not None else self.use_airllm
        if (
            not use_quant
            or not self.airllm_manager
            or not self.airllm_manager.airllm_available
        ):
            return await self._ollama_chat(model_name, messages)
        try:
            hf_name = self._map_ollama_to_hf(model_name)
            quant = QuantizationLevel(self.default_quantization)
            model = self.airllm_manager.load_model(hf_name, quant)
            prompt = self._format_messages(messages)
            return self.airllm_manager.generate(model, prompt)
        except Exception as exc:
            print(f"AirLLM chat failed: {exc}. Falling back to Ollama.")
            return await self._ollama_chat(model_name, messages)

    async def _ollama_chat(self, model_name: str, messages: List[Dict[str, str]]) -> str:
        import ollama

        response = ollama.chat(model=model_name, messages=messages)
        return response["message"]["content"]

    def _map_ollama_to_hf(self, ollama_name: str) -> str:
        mapping = {
            "llama3.1:8b": "meta-llama/Llama-3.1-8B-Instruct",
            "llama3.1:70b": "meta-llama/Llama-3.1-70B-Instruct",
            "codellama:7b": "codellama/CodeLlama-7b-Instruct-hf",
            "mistral:7b": "mistralai/Mistral-7B-Instruct-v0.2",
        }
        return mapping.get(ollama_name, ollama_name)

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"{role.title()}: {content}\n")
        parts.append("Assistant: ")
        return "\n".join(parts)
