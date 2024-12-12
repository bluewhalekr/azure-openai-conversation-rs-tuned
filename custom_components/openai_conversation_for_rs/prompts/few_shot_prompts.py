"""Few-shot prompts for Home Assistant template queries"""

tv_on_off_example = [
    {"role": "user", "content": "티비 켜줘"},
    {
        "role": "assistant",
        "content": "크롬캐스트를 이용하여 TV 전원을 킵니다",
        "tool_calls": [
            {
                "id": "call_azg0GnUsNXXkDfkDMyr9BZCG",
                "function": {
                    "arguments": '{"method":"post","endpoint":"/api/services/media_player/turn_on","body":{"entity_id":"media_player.samusil_2"}}',
                    "name": "home_assistant_api",
                },
                "type": "function",
            }
        ],
    },
    {"role": "tool", "content": '{"status_code": 200, "text": "[]"}', "tool_call_id": "call_azg0GnUsNXXkDfkDMyr9BZCG"},
    {"role": "user", "content": "유튜브로 qwer 검색해줘"},
    {"role": "assistant", "content": "youtube_domain_flg"},
]
