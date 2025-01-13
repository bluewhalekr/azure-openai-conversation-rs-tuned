import logging
from datetime import datetime
from typing import List

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr

_LOGGER = logging.getLogger(__name__)


class HaCrawler:
    """Class to crawl Home Assistant data"""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._device_registry = dr.async_get(hass)
        self._area_registry = ar.async_get(hass)

    def get_ha_states(self) -> dict:
        """Get the Home Assistant contexts."""
        now = datetime.now()

        # 시간 관련 컨텍스트 구성
        context = {
            "time": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "weekday": now.strftime("%A"),
            "entities": [],
        }

        # 모든 엔티티 상태 수집
        for entity_id in self.hass.states.async_entity_ids():
            state = self.hass.states.get(entity_id)
            if not state:
                continue

            # 디바이스 정보 가져오기
            device_id = state.attributes.get("device_id")
            device = None
            if device_id:
                device = self._device_registry.async_get(device_id)

            # 영역 정보 가져오기
            area_id = state.attributes.get("area_id")
            area = None
            if area_id:
                area = self._area_registry.async_get_area(area_id)

            entity_info = {
                "entity_id": entity_id,
                "name": state.attributes.get("friendly_name", entity_id),
                "state": state.state,
                "domain": entity_id.split(".")[0],
                "device": {
                    "id": device_id,
                    "name": device.name if device else None,
                    "name_by_user": device.name_by_user if device else None,
                    "model": device.model if device else None,
                    "manufacturer": device.manufacturer if device else None,
                }
                if device
                else None,
                "area": {"id": area_id, "name": area.name if area else None} if area else None,
                "labels": state.attributes.get("labels", []),
            }

            context["entities"].append(entity_info)

        return self.filter_states(context)

    def get_services(self) -> List[dict]:
        """Get the Home Assistant services."""
        services = []

        # 서비스 정보 수집
        for domain, domain_services in self.hass.services.async_services().items():
            service_info = {"domain": domain, "services": {}}

            for service_name, service_data in domain_services.items():
                service_info["services"][service_name] = {
                    "name": service_name,
                    "description": getattr(service_data, "description", "No description available"),
                    "fields": getattr(service_data, "fields", {}),
                }

            services.append(service_info)

        return self.filter_services(services)

    def filter_states(self, states: dict) -> dict:
        """Filter the Home Assistant states."""
        to_filter_domain = [
            "update",
            "tts",
            "conversation",
            "person",
            "zone",
            "sun",
            "todo",
            "binary_sensor",
        ]
        to_filter_entity_id = [
            "binary_sensor.rpi_power_status",
            "device_tracker.sm_s926n",
            "sensor.sm_s926n_battery_level",
            "sensor.sm_s926n_battery_state",
            "sensor.sm_s926n_charger_type",
            "script.script",
            "sensor.sun_next_noon",
            "sensor.sun_next_rising",
            "sensor.sun_next_setting",
            "sensor.speaker_status",
            "sensor.sun_next_dusk",
            "sensor.sun_next_midnight",
            "sensor.sun_next_dawn",
            "number.geosildeung_smooth_on",
            "number.geosildeung_smooth_off",
            "select.geosildeung_light_preset",
            "sensor.geosildeung_signal_level",
            "switch.geosildeung_auto_update_enabled",
            "number.cimsil_deung_smooth_on",
            "number.cimsil_deung_smooth_off",
            "select.cimsil_deung_light_preset",
            "sensor.cimsil_deung_signal_level",
            "switch.cimsil_deung_auto_update_enabled",
            "number.geosil_teibeul_seutaendeu_deung_smooth_on",
            "number.geosil_teibeul_seutaendeu_deung_smooth_off",
            "select.geosil_teibeul_seutaendeu_deung_light_preset",
            "sensor.geosil_teibeul_seutaendeu_deung_signal_level",
            "switch.geosil_teibeul_seutaendeu_deung_auto_update_enabled",
            "number.hwajangsil_deung_smooth_on",
            "number.hwajangsil_deung_smooth_off",
            "select.hwajangsil_deung_light_preset",
            "sensor.hwajangsil_deung_signal_level",
            "switch.hwajangsil_deung_auto_update_enabled",
            "sensor.robosceongsogi_sensor_dirty_left",
            "sensor.robosceongsogi_filter_left",
            "sensor.robosceongsogi_side_brush_left",
            "sensor.robosceongsogi_main_brush_left",
            "sensor.robosceongsogi_last_clean_area",
            "sensor.robosceongsogi_current_clean_area",
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

    def filter_services(self, services: List[dict]) -> List[dict]:
        """Filter the Home Assistant services."""
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
            "mqtt",
            "weather",
            "timer",
            "openai_stt_rs",
            "schedule",
            "todo",
        ]

        return [service for service in services if service.get("domain") not in to_filter_domain]
