from config import NormalizationConfig
from linkedin_tool.normalization.llm import GroqLLMNormalizer
from linkedin_tool.schema import ScrapeResult

api_key = NormalizationConfig.GROQ_API_KEYS.value[0]
normalizer = GroqLLMNormalizer(api_key=api_key)

print(normalizer.normalize_batch("title", ["data engineer intern", "	web developer intern"]))