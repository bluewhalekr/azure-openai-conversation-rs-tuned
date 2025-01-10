"""Constants for the Azure OpenAI GPT conversation RS-Tuned integration."""

DOMAIN = "azure_openai_conversation_rs_tuned"
CONF_ENDPOINT = "endpoint"
CONF_DEPLOYMENT_NAME = "deployment_name"
DEFAULT_LANGUAGE = "ko"
CONVERSATION_AGENT_NAME = "GPT_RS_TUNED"
API_VERSION = "2024-08-01-preview"
FIXED_ENDPOINT = "https://remote-solution-fine-tuning.openai.azure.com/"
CACHE_ENDPOINT = "https://rs-audio-router.azurewebsites.net/api/v1/cache-routing"
PATTERN_ENDPOINT = "https://rs-command-crawler.azurewebsites.net/api/v1/cache-routing"
# TO REMOVE AFTER DEMO
BLENDER_BRIDGE_ENDPOINT = "http://20.249.196.104:8000"
BLENDER_LIGHT_ENTITY = [
    "geosildeung",
    "geosil_teibeul_seutaendeu_deung",
    "geosil_sofa_stand_deung",
    "geosil_pendant_deung",
    "cimsil_deung",
    "cimsil_chichim_deung",
    "cimsil_stand_deung",
    "hwajangsil_deung",
    "jubang_deung",
]
BLENDER_DEVICE_ENTITY = ["chromecast", "seonpunggi", "robosceongsogi", "gonggiceongjeonggi"]
