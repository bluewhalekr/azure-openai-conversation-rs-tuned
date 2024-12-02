"""Module to crawl Home Assistant data"""

import json
import logging
import re
import urllib.parse
from typing import List, Union

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HA_CONTEXT_TEMPLATE_QUERY = """
{% set time = now().strftime("%H:%M:%S") %}
{% set date = now().strftime("%Y-%m-%d") %}
{% set weekday = now().strftime("%A") %}
{% set context = namespace(time=time, date=date, weekday=weekday, entities=[]) %}

{% for state in states %}
    {% set context = context %}
    {% set entity_id = state.entity_id %}

    {% set device_connections = device_attr(entity_id, 'connections') %}
    {% if device_connections %}
        {% set device_connections = device_connections|list %}
    {% else %}
        {% set device_connections = [] %}
    {% endif %}

    {% set entity_item = dict(
        entity_id=entity_id,
        name=state.name,
        state=state.state,
        domain=state.domain,
        device=dict(
            id=entity_id,
            name=device_attr(entity_id, 'name'),
            name_by_user=device_attr(entity_id, 'name_by_user'),
            model=device_attr(entity_id, 'model'),
            manufacturer=device_attr(entity_id, 'manufacturer'),
            ),
        area=dict(
            id=area_id(entity_id),
            name=area_name(entity_id)
            ),
        floor=dict(
            id=floor_id(entity_id),
            name=floor_name(entity_id)
            ),
        labels=labels(entity_id),
        ) 
    %}
    {% set context.entities = context.entities + [entity_item] %}
{% endfor %}

{{ dict(
    time=context.time,
    date=context.date,
    weekday=context.weekday,
    entities=context.entities
    )
}}
"""


class HaRequest:
    """Class to handle Home Assistant API requests."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.headers = self.to_api_header(token)

    @staticmethod
    def to_api_header(token):
        """Create a header for Home Assistant API requests."""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get(self, endpoint) -> requests.Response:
        """Send a GET request to Home Assistant."""
        url = urllib.parse.urljoin(self.base_url, endpoint)
        return requests.get(url, headers=self.headers, timeout=5)

    def post(self, endpoint, data) -> requests.Response:
        """Send a POST request to Home Assistant."""
        url = urllib.parse.urljoin(self.base_url, endpoint)
        return requests.post(url, headers=self.headers, json=data, timeout=5)


class HaCrawler:
    """Class to crawl Home Assistant data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the crawler with Home Assistant instance and config entry."""
        self.hass = hass
        # Home Assistant 인스턴스의 내부 URL 사용
        self.base_url = "http://supervisor/core"
        # Config Entry에서 토큰 가져오기
        self.tokens = entry.data[CONF_API_KEY]
        self.ha_request = HaRequest(self.base_url, self.tokens)

    def is_connected(self) -> bool:
        """Check if the Home Assistant is connected."""
        endpoint = "/api/"
        if self.base_url and self.tokens:
            response = self.ha_request.get(endpoint)
            if response.status_code == 200:
                return True
            _LOGGER.error(response.text)
            return False

        return False

    def _api_template_query(self, template) -> requests.Response:
        """Send a template query to Home"""
        endpoint = "/api/template"
        data = {"template": template}
        response = self.ha_request.post(endpoint, data)

        return response

    @staticmethod
    def template_result_to_dict(result_text) -> Union[dict, List[dict]]:
        """Convert the template result to a dictionary."""
        result_text = result_text.replace('"', "`")
        result_text = result_text.replace("'", '"')
        result_text = result_text.replace("True", "true")
        result_text = result_text.replace("False", "false")
        result_text = result_text.replace("None", "null")
        result_text = re.sub(r"}\s+{", "}, {", result_text)
        result_text = re.sub(r"<([^:]+): ([^>]+)>", r'{"\1": \2}', result_text)
        result_text = result_text.replace("(", "[")
        result_text = result_text.replace(")", "]")

        if result_text.startswith("{"):
            result_text = "[" + result_text

        if result_text.endswith("}"):
            result_text = result_text + "]"

        try:
            return json.loads(result_text)

        except json.JSONDecodeError as e:
            raise e

    @staticmethod
    def filter_states(states):
        """Filter the Home Assistant states."""
        to_filter_domain = ["update", "tts"]
        to_filter_entity_id = [
            "binary_sensor.rpi_power_status",
            "device_tracker.sm_s926n",
            "sensor.sm_s926n_battery_level",
            "sensor.sm_s926n_battery_state",
            "sensor.sm_s926n_charger_type",
        ]

        filtered_entities = []
        for entity in states["entities"]:
            entity_id = entity.get("entity_id")
            domain = entity.get("domain")
            if domain in to_filter_domain or entity_id in to_filter_entity_id:
                continue

            filtered_entities.append(entity)

        states["entities"] = filtered_entities
        return states

    @staticmethod
    def filter_services(services: List[dict]) -> List[dict]:
        """Filter the Home Assistant states."""
        to_filter_domain = [
            "homeassistant",
            "persistent_notification",
            "system_log",
            "logger",
            "person",
            "frontend",
            "recorder",
            "hassio",
            "update",
            "cloud",
            "ffmpeg",
            "tts",
            "scene",
            "input_button",
            "logbook",
            "script",
            "input_select",
            "input_boolean",
            "input_number",
            "zone",
            "conversation",
            "input_datetime",
            "shopping_list",
            "input_text",
            "counter",
            "openai_conversation",
            "button",
            "notify",
            "device_tracker",
            "number",
            "select",
        ]

        filtered = []
        for service in services:
            domain = service.get("domain")
            if domain in to_filter_domain:
                continue

            filtered.append(service)

        return filtered

    def get_ha_states(self) -> dict:
        """Get the Home Assistant contexts."""
        template = HA_CONTEXT_TEMPLATE_QUERY
        response = self._api_template_query(template)

        if response.status_code == 200:
            if response.text:
                result = self.template_result_to_dict(response.text)[0]
                return self.filter_states(result)

            raise ValueError("No data returned from Home Assistant")

        raise requests.HTTPError(response.text)

    def get_services(self) -> List[dict]:
        """Get the Home Assistant services."""
        endpoint = "/api/services"
        response = self.ha_request.get(endpoint)

        if response.status_code != 200:
            raise requests.HTTPError(response.text)

        result = response.json()
        return self.filter_services(result)
