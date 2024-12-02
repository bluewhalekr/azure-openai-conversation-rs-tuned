# Automation Trigger
Triggers are what starts the processing of an automation rule. When any of the automation’s triggers becomes true (trigger fires), Home Assistant will validate the conditions, if any, and call the action.
An automation can be triggered by an event, a certain entity state, at a given time, and more. These can be specified directly or more flexible via templates. It is also possible to specify multiple triggers for one automation.


## Trigger ID
All triggers can be assigned an optional id. If the ID is omitted, it will instead be set to the index of the trigger. The id can be referenced from trigger conditions and actions. The id does not have to be unique for each trigger, and it can be used to group similar triggers for use later in the automation (i.e., several triggers of different types that should all turn some entity on).
```yaml
automation:
  triggers:
    - trigger: event
      event_type: "MY_CUSTOM_EVENT"
      id: "custom_event"
    - trigger: mqtt
      topic: "living_room/switch/ac"
      id: "ac_on"
    - trigger: state  # This trigger will be assigned id="2"
      entity_id:
        - device_tracker.paulus
        - device_tracker.anne_therese
      to: "home"
```

## Trigger variables
There are two different types of variables available for triggers. Both work like script level variables.
The first variant allows you to define variables that will be set when the trigger fires. The variables will be able to use templates and have access to the trigger variable.
The second variant is setting variables that are available when attaching a trigger when the trigger can contain templated values. These are defined using the trigger_variables key at an automation level. These variables can only contain limited templates. The triggers will not re-apply if the value of the template changes. Trigger variables are a feature meant to support using blueprint inputs in triggers.
```yaml
automation:
  trigger_variables:
    my_event: example_event
  triggers:
    - trigger: event
      # Able to use `trigger_variables`
      event_type: "{{ my_event }}"
      # These variables are evaluated and set when this trigger is triggered
      variables:
        name: "{{ trigger.event.data.name }}"
```

## Event trigger
An event trigger fires when an event is being received. Events are the raw building blocks of Home Assistant. You can match events on just the event name or also require specific event data or context to be present.
Events can be fired by integrations or via the API. There is no limitation to the types.
```yaml
automation:
  triggers:
    - trigger: event
      event_type: "MY_CUSTOM_EVENT"
      # optional
      event_data:
        mood: happy
      context:
        user_id:
        # any of these will match
          - "MY_USER_ID"
          - "ANOTHER_USER_ID"
```
It is also possible to listen for multiple events at once. This is useful for event that contain no, or similar, data and contexts.
```yaml
automation:
  triggers:
    - trigger: event
      event_type:
        - automation_reloaded
        - scene_reloaded
```
It’s also possible to use limited templates in the event_type, event_data and context options.

The event_type, event_data and context templates are only evaluated when setting up the trigger, they will not be reevaluated for every event.
```yaml
automation:
  trigger_variables:
    sub_event: ABC
    node: ac
    value: on
  triggers:
    - trigger: event
      event_type: "{{ 'MY_CUSTOM_EVENT_' ~ sub_event }}"
```

## Numeric state trigger
Fires when the numeric value of an entity’s state (or attribute’s value if using the attribute property, or the calculated value if using the value_template property) crosses a given threshold (equal excluded). On state change of a specified entity, attempts to parse the state as a number and fires if the value is changing from above to below or from below to above the given threshold (equal excluded).
Crossing the threshold means that the trigger only fires if the state wasn’t previously within the threshold. If the current state of your entity is 50 and you set the threshold to below: 75, the trigger would not fire if the state changed to e.g. 49 or 72 because the threshold was never crossed. The state would first have to change to e.g. 76 and then to e.g. 74 for the trigger to fire.
```yaml
automation:
  triggers:
    - trigger: numeric_state
      entity_id: sensor.temperature
      # If given, will trigger when the value of the given attribute for the given entity changes..
      attribute: attribute_name
      # ..or alternatively, will trigger when the value given by this evaluated template changes.
      value_template: "{{ state.attributes.value - 5 }}"
      # At least one of the following required
      above: 17
      below: 25
      # If given, will trigger when the condition has been true for X time; you can also use days and milliseconds.
      for:
        hours: 1
        minutes: 10
        seconds: 5
```
When the attribute option is specified the trigger is compared to the given attribute instead of the state of the entity.
```yaml
automation:
  triggers:
    - trigger: numeric_state
      entity_id: climate.kitchen
      attribute: current_temperature
      above: 23
```
More dynamic and complex calculations can be done with value_template. The variable ‘state’ is the state object of the entity specified by entity_id.

The state of the entity can be referenced like this:
```yaml
automation:
  triggers:
    - trigger: numeric_state
      entity_id: sensor.temperature
      value_template: "{{ state.state | float * 9 / 5 + 32 }}"
      above: 70
```
Attributes of the entity can be referenced like this:
```yaml
automation:
  triggers:
    - trigger: numeric_state
      entity_id: climate.kitchen
      value_template: "{{ state.attributes.current_temperature - state.attributes.temperature_set_point }}"
      above: 3
```

Listing above and below together means the numeric_state has to be between the two values. In the example above, the trigger would fire a single time if a numeric_state goes into the 17.1-24.9 range (above 17 and below 25). It will only fire again, once it has left the defined range and enters it again.
Number helpers (input_number entities), number, sensor, and zone entities that contain a numeric value, can be used in the above and below thresholds. However, the comparison will only be made when the entity specified in the trigger is updated. This would look like:
```yaml
automation:
  triggers:
    - trigger: numeric_state
      entity_id: sensor.outside_temperature
      # Other entity ids can be specified for above and/or below thresholds
      above: sensor.inside_temperature
```
The for: can also be specified as HH:MM:SS like this:
```yaml
automation:
  triggers:
    - trigger: numeric_state
      entity_id: sensor.temperature
      # At least one of the following required
      above: 17
      below: 25

      # If given, will trigger when condition has been for X time.
      for: "01:10:05"
```
You can also use templates in the for option.
```yaml
automation:
  triggers:
    - trigger: numeric_state
      entity_id:
        - sensor.temperature_1
        - sensor.temperature_2
      above: 80
      for:
        minutes: "{{ states('input_number.high_temp_min')|int }}"
        seconds: "{{ states('input_number.high_temp_sec')|int }}"
  actions:
    - action: persistent_notification.create
      data:
        message: >
          {{ trigger.to_state.name }} too high for {{ trigger.for }}!
```
The for template(s) will be evaluated when an entity changes as specified.

Use of the for option will not survive Home Assistant restart or the reload of automations. During restart or reload, automations that were awaiting for the trigger to pass, are reset.
If for your use case this is undesired, you could consider using the automation to set an input_datetime to the desired time and then use that input_datetime as an automation trigger to perform the desired actions at the set time.

## State trigger
In general, the state trigger fires when the state of any of given entities changes. The behavior is as follows:

If only the entity_id is given, the trigger fires for all state changes, even if only a state attribute changed.
If at least one of from, to, not_from, or not_to are given, the trigger fires on any matching state change, but not if only an attribute changed.
To trigger on all state changes, but not on changed attributes, set at least one of from, to, not_from, or not_to to null.
Use of the for option doesn’t survive a Home Assistant restart or the reload of automations.
During restart or reload, automations that were awaiting for the trigger to pass, are reset.
If for your use case this is undesired, you could consider using the automation to set an input_datetime to the desired time and then use that input_datetime as an automation trigger to perform the desired actions at the set time.

The values you see in your overview will often not be the same as the actual state of the entity. For instance, the overview may show Connected when the underlying entity is actually on. You should check the state of the entity by checking the states in the developer tool, under Developer Tools > States.

### Examples
This automation triggers if either Paulus or Anne-Therese are home for one minute.
```yaml
automation:
  triggers:
    - trigger: state
      entity_id:
        - device_tracker.paulus
        - device_tracker.anne_therese
      # Optional
      from: "not_home"
      # Optional
      to: "home"
      # If given, will trigger when the condition has been true for X time; you can also use days and milliseconds.
      for:
        hours: 0
        minutes: 1
        seconds: 0
```
It’s possible to give a list of from states or to states:
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: vacuum.test
      from:
        - "cleaning"
        - "returning"
      to: "error"
```
If you want to trigger on all state changes, but not on attribute changes, you can to to null (this would also work by setting from, not_from, or not_to to null):
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: vacuum.test
      to:
```
If you want to trigger on all state changes except specific ones, use not_from or not_to The not_from and not_to options are the counter parts of from and to. They can be used to trigger on state changes that are not the specified state.
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: vacuum.test
      not_from:
        - "unknown"
        - "unavailable"
      to: "on"
```
You cannot use from and not_from at the same time. The same applies to to and not_to.

### Triggering on attribute changes
When the attribute option is specified, the trigger only fires when the specified attribute changes. Changes to other attributes or state changes are ignored.

For example, this trigger only fires when the boiler has been heating for 10 minutes:
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: climate.living_room
      attribute: hvac_action
      to: "heating"
      for: "00:10:00"
```
This trigger fires whenever the boiler’s hvac_action attribute changes:
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: climate.living_room
      attribute: hvac_action
```
### Holding a state or attribute
You can use for to have the state trigger only fire if the state holds for some time.

This example fires, when the entity state changed to "on" and holds that state for 30 seconds:
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: light.office
      # Must stay "on" for 30 seconds
      to: "on"
      for: "00:00:30"
```
When holding a state, changes to attributes are ignored. Changes to attributes don’t cancel the hold time.

You can also fire the trigger when the state value changed from a specific state, but hasn’t returned to that state value for the specified time.

This can be useful, e.g., checking if a media player hasn’t turned “off” for the time specified, but doesn’t care about “playing” or “paused”.
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: media_player.kitchen
      # Not "off" for 30 minutes
      from: "off"
      for: "00:30:00"
```
Please note, that when using from, to and for, only the value of the to option is considered for the time specified.

In this example, the trigger fires if the state value of the entity remains the same for for the time specified, regardless of the current state value.
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: media_player.kitchen
      # The media player remained in its current state for 1 hour
      for: "01:00:00"
```
You can also use templates in the for option.
```yaml
automation:
  triggers:
    - trigger: state
      entity_id:
        - device_tracker.paulus
        - device_tracker.anne_therese
      to: "home"
      for:
        minutes: "{{ states('input_number.lock_min')|int }}"
        seconds: "{{ states('input_number.lock_sec')|int }}"
  actions:
    - action: lock.lock
      target:
        entity_id: lock.my_place
```
The for template(s) will be evaluated when an entity changes as specified.


## Sun trigger
### Sunset / Sunrise trigger
Fires when the sun is setting or rising, i.e., when the sun elevation reaches 0°.
An optional time offset can be given to have it fire a set time before or after the sun event (e.g., 45 minutes before sunset). A negative value makes it fire before sunrise or sunset, a positive value afterwards. The offset needs to be specified in number of seconds, or in a hh:mm:ss format.

Since the duration of twilight is different throughout the year, it is recommended to use sun elevation triggers instead of sunset or sunrise with a time offset to trigger automations during dusk or dawn.
```yaml
automation:
  triggers:
    - trigger: sun
      # Possible values: sunset, sunrise
      event: sunset
      # Optional time offset. This example will trigger 45 minutes before sunset.
      offset: "-00:45:00"
```
### Sun elevation trigger
Sometimes you may want more granular control over an automation than simply sunset or sunrise and specify an exact elevation of the sun. This can be used to layer automations to occur as the sun lowers on the horizon or even after it is below the horizon. This is also useful when the “sunset” event is not dark enough outside and you would like the automation to run later at a precise solar angle instead of the time offset such as turning on exterior lighting. For most automations intended to run during dusk or dawn, a number between 0° and -6° is suitable; -4° is used in this example:
```yaml
automation:
  - alias: "Exterior Lighting on when dark outside"
    triggers:
      - trigger: numeric_state
        entity_id: sun.sun
        attribute: elevation
        # Can be a positive or negative number
        below: -4.0
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.exterior_lighting
```
If you want to get more precise, you can use this solar calculator, which will help you estimate what the solar elevation will be at any specific time. Then from this, you can select from the defined twilight numbers.

Although the actual amount of light depends on weather, topography and land cover, they are defined as:

* Civil twilight: 0° > Solar angle > -6°
  This is what is meant by twilight for the average person: Under clear weather conditions, civil twilight approximates the limit at which solar illumination suffices for the human eye to clearly distinguish terrestrial objects. Enough illumination renders artificial sources unnecessary for most outdoor activities.
* Nautical twilight: -6° > Solar angle > -12°
* Astronomical twilight: -12° > Solar angle > -18°

A very thorough explanation of this is available in the Wikipedia article about the Twilight.

## Tag trigger
Fires when a tag is scanned. For example, a NFC tag is scanned using the Home Assistant Companion mobile application.
```yaml
automation:
  triggers:
    - trigger: tag
      tag_id: A7-6B-90-5F
```
Additionally, you can also only trigger if a card is scanned by a specific device/scanner by setting the device_id:
```yaml
automation:
  triggers:
    - trigger: tag
      tag_id: A7-6B-90-5F
      device_id: 0e19cd3cf2b311ea88f469a7512c307d
```
Or trigger on multiple possible devices for multiple tags:
```yaml
automation:
  triggers:
    - trigger: tag
      tag_id:
        - "A7-6B-90-5F"
        - "A7-6B-15-AC"
      device_id:
        - 0e19cd3cf2b311ea88f469a7512c307d
        - d0609cb25f4a13922bb27d8f86e4c821
```
## Template trigger
Template triggers work by evaluating a template when any of the recognized entities change state. The trigger will fire if the state change caused the template to render ‘true’ (a non-zero number or any of the strings true, yes, on, enable) when it was previously ‘false’ (anything else).

This is achieved by having the template result in a true boolean expression (for example {{ is_state('device_tracker.paulus', 'home') }}) or by having the template render true (example below).

With template triggers you can also evaluate attribute changes by using is_state_attr (like {{ is_state_attr('climate.living_room', 'away_mode', 'off') }})
```yaml
automation:
  triggers:
    - trigger: template
      value_template: "{% if is_state('device_tracker.paulus', 'home') %}true{% endif %}"

      # If given, will trigger when template remains true for X time.
      for: "00:01:00"
```
You can also use templates in the for option.
```yaml
automation:
  triggers:
    - trigger: template
      value_template: "{{ is_state('device_tracker.paulus', 'home') }}"
      for:
        minutes: "{{ states('input_number.minutes')|int(0) }}"
```
The for template(s) will be evaluated when the value_template becomes ‘true’.

Templates that do not contain an entity will be rendered once per minute.

Use of the for option will not survive Home Assistant restart or the reload of automations. During restart or reload, automations that were awaiting for the trigger to pass, are reset.
If for your use case this is undesired, you could consider using the automation to set an input_datetime to the desired time and then use that input_datetime as an automation trigger to perform the desired actions at the set time.

## Time trigger
The time trigger is configured to fire once a day at a specific time, or at a specific time on a specific date. There are three allowed formats:

### Time string
A string that represents a time to fire on each day. Can be specified as HH:MM or HH:MM:SS. If the seconds are not specified, :00 will be used.
```yaml
automation:
  - triggers:
    - trigger: time
      # Military time format. This trigger will fire at 3:32 PM
      at: "15:32:00"
```
### Input datetime
The entity ID of an input datetime.

has_date	has_time	Description
true	true	Will fire at specified date & time.
true	false	Will fire at midnight on specified date.
false	true	Will fire once a day at specified time.
```yaml
automation:
  - triggers:
      - trigger: state
        entity_id: binary_sensor.motion
        to: "on"
    actions:
      - action: climate.turn_on
        target:
          entity_id: climate.office
      - action: input_datetime.set_datetime
        target:
          entity_id: input_datetime.turn_off_ac
        data:
          datetime: >
            {{ (now().timestamp() + 2*60*60)
               | timestamp_custom('%Y-%m-%d %H:%M:%S') }}
  - triggers:
      - trigger: time
        at: input_datetime.turn_off_ac
    actions:
      - action: climate.turn_off
        target:
          entity_id: climate.office
```
### Sensors of datetime device class
The Entity ID of a sensor with the “timestamp” device class.
```yaml
automation:
  - triggers:
      - trigger: time
        at: sensor.phone_next_alarm
    actions:
      - action: light.turn_on
        target:
          entity_id: light.bedroom
```
Sensors of datetime device class with offsets
When the time is provided using a sensor of the timestamp device class, an offset can be provided. This offset will be added to (or subtracted from when negative) the sensor value.

For example, this trigger fires 5 minutes before the phone alarm goes off.
```yaml
automation:
  - triggers:
      - trigger: time
        at:
          entity_id: sensor.phone_next_alarm
          offset: -00:05:00
    actions:
      - action: light.turn_on
        target:
          entity_id: light.bedroom
```

When using a positive offset the trigger might never fire. This is due to the sensor changing before the offset is reached. For example, when using a phone alarm as a trigger, the sensor value will change to the new alarm time when the alarm goes off, which means this trigger will change to the new time as well.

### Multiple times
Multiple times can be provided in a list. All formats can be intermixed.
```yaml
automation:
  triggers:
    - trigger: time
      at:
        - input_datetime.leave_for_work
        - "18:30:00"
        - entity_id: sensor.bus_arrival
          offset: "-00:10:00"
```
### Limited templates
It’s also possible to use limited templates for times.
```yaml
blueprint:
  input:
    alarm:
      name: Alarm
      selector:
        text:
    hour:
      name: Hour
      selector:
        number:
          min: 0
          max: 24

  trigger_variables:
    my_alarm: !input alarm
    my_hour: !input hour
  trigger:
    - platform: time
      at:
      - "sensor._time"
      - ":30:00"
```
## Time pattern trigger
With the time pattern trigger, you can match if the hour, minute or second of the current time matches a specific value. You can prefix the value with a / to match whenever the value is divisible by that number. You can specify * to match any value (when using the web interface this is required, the fields cannot be left empty).
```yaml
automation:
  triggers:
    - trigger: time_pattern
      # Matches every hour at 5 minutes past whole
      minutes: 5

automation 2:
  triggers:
    - trigger: time_pattern
      # Trigger once per minute during the hour of 3
      hours: "3"
      minutes: "*"

automation 3:
  triggers:
    - trigger: time_pattern
      # You can also match on interval. This will match every 5 minutes
      minutes: "/5"
```

Do not prefix numbers with a zero - using '01' instead of '1' for example will result in errors.

## Persistent notification trigger
Persistent notification triggers are fired when a persistent_notification is added or removed that matches the configuration options.
```yaml
automation:
  triggers:
    - trigger: persistent_notification
      update_type:
        - added
        - removed
      notification_id: invalid_config
```
See the Persistent Notification integration for more details on event triggers and the additional event data available for use by an automation.

## Webhook trigger
Webhook trigger fires when a web request is made to the webhook endpoint: /api/webhook/<webhook_id>. The webhook endpoint is created automatically when you set it as the webhook_id in an automation trigger.
```yaml
automation:
  triggers:
    - trigger: webhook
      webhook_id: "some_hook_id"
      allowed_methods:
        - POST
        - PUT
      local_only: true
```
You can run this automation by sending an HTTP POST request to http://your-home-assistant:8123/api/webhook/some_hook_id. Here is an example using the curl command line program, with an example form data payload:
```bash
curl -X POST -d 'key=value&key2=value2' https://your-home-assistant:8123/api/webhook/some_hook_id
```
Webhooks support HTTP POST, PUT, HEAD, and GET requests; PUT requests are recommended. HTTP GET and HEAD requests are not enabled by default but can be enabled by adding them to the allowed_methods option. The request methods can also be configured in the UI by clicking the settings gear menu button beside the Webhook ID.
By default, webhook triggers can only be accessed from devices on the same network as Home Assistant or via Nabu Casa Cloud webhooks. The local_only option should be set to false to allow webhooks to be triggered directly via the internet. This option can also be configured in the UI by clicking the settings gear menu button beside the Webhook ID.
Remember to use an HTTPS URL if you’ve secured your Home Assistant installation with SSL/TLS.

Note that a given webhook can only be used in one automation at a time. That is, only one automation trigger can use a specific webhook ID.

### Webhook data
Payloads may either be encoded as form data or JSON. Depending on that, its data will be available in an automation template as either trigger.data or trigger.json. URL query parameters are also available in the template as trigger.query.

Note that to use JSON encoded payloads, the Content-Type header must be set to application/json, e.g.:
```bash
curl -X POST -H "Content-Type: application/json" -d '{ "key": "value" }' https://your-home-assistant:8123/api/webhook/some_hook_id
```
### Webhook security
Webhook endpoints don’t require authentication, other than knowing a valid webhook ID. Security best practices for webhooks include:

Do not use webhooks to trigger automations that are destructive, or that can create safety issues. For example, do not use a webhook to unlock a lock, or open a garage door.
Treat a webhook ID like a password: use a unique, non-guessable value, and keep it secret.
Do not copy-and-paste webhook IDs from public sources, including blueprints. Always create your own.
Keep the local_only option enabled for webhooks if access from the internet is not required.
## Zone trigger
Zone trigger fires when an entity is entering or leaving the zone. The entity can be either a person, or a device_tracker. For zone automation to work, you need to have setup a device tracker platform that supports reporting GPS coordinates. This includes GPS Logger, the OwnTracks platform and the iCloud platform.
```yaml
automation:
  triggers:
    - trigger: zone
      entity_id: person.paulus
      zone: zone.home
      # Event is either enter or leave
      event: enter # or "leave"
```
Geolocation trigger
Geolocation trigger fires when an entity is appearing in or disappearing from a zone. Entities that are created by a Geolocation platform support reporting GPS coordinates. Because entities are generated and removed by these platforms automatically, the entity ID normally cannot be predicted. Instead, this trigger requires the definition of a source, which is directly linked to one of the Geolocation platforms.

This isn’t for use with device_tracker entities. For those look above at the zone trigger.
```yaml
automation:
  triggers:
    - trigger: geo_location
      source: nsw_rural_fire_service_feed
      zone: zone.bushfire_alert_zone
      # Event is either enter or leave
      event: enter # or "leave"
```
## Device triggers
Device triggers encompass a set of events that are defined by an integration. This includes, for example, state changes of sensors as well as button events from remotes. MQTT device triggers are set up through autodiscovery.

In contrast to state triggers, device triggers are tied to a device and not necessarily an entity. To use a device trigger, set up an automation through the browser frontend. If you would like to use a device trigger for an automation that is not managed through the browser frontend, you can copy the YAML from the trigger widget in the frontend and paste it into your automation’s trigger list.

## Calendar trigger
Calendar trigger fires when a Calendar event starts or ends, allowing for much more flexible automations than using the Calendar entity state which only supports a single event start at a time.

An optional time offset can be given to have it fire a set time before or after the calendar event (e.g., 5 minutes before event start).
```yaml
automation:
  triggers:
    - trigger: calendar
      # Possible values: start, end
      event: start
      # The calendar entity_id
      entity_id: calendar.light_schedule
      # Optional time offset
      offset: "-00:05:00"
```
See the Calendar integration for more details on event triggers and the additional event data available for use by an automation.

## Sentence trigger
A sentence trigger fires when Assist matches a sentence from a voice assistant using the default conversation agent. Sentence triggers only work with Home Assistant Assist. External conversation agents such as OpenAI or Google Generative AI cannot be used to trigger automations.

Sentences are allowed to use some basic template syntax like optional and alternative words. For example, [it's ]party time will match both “party time” and “it’s party time”.
```yaml
automation:
  triggers:
    - trigger: conversation
      command:
        - "[it's ]party time"
        - "happy (new year|birthday)"
```
The sentences matched by this trigger will be:

party time
it’s party time
happy new year
happy birthday
Punctuation and casing are ignored, so “It’s PARTY TIME!!!” will also match.

### Sentence wildcards
Adding one or more {lists} to your trigger sentences will capture any text at that point in the sentence. A slots object will be available in the trigger data. This allows you to match sentences with variable parts, such as album/artist names or a description of a picture.

For example, the sentence play {album} by {artist} will match “play the white album by the beatles” and have the following variables available in the action templates:

{{ trigger.slots.album }} - “the white album”
{{ trigger.slots.artist }} - “the beatles”
Wildcards will match as much text as possible, which may lead to surprises: “play day by day by taken by trees” will match album as “day” and artist as “day by taken by trees”. Including extra words in your template can help: play {album} by artist {artist} can now correctly match “play day by day by artist taken by trees”.

## Multiple triggers
It is possible to specify multiple triggers for the same rule. To do so just prefix the first line of each trigger with a dash (-) and indent the next lines accordingly. Whenever one of the triggers fires, processing of your automation rule begins.
```yaml
automation:
  triggers:
    # first trigger
    - trigger: time_pattern
      minutes: 5
      # our second trigger is the sunset
    - trigger: sun
      event: sunset
```
## Multiple entity IDs for the same trigger
It is possible to specify multiple entities for the same trigger. To do so add multiple entities using a nested list. The trigger will fire and start, processing your automation each time the trigger is true for any entity listed.
```yaml
automation:
  triggers:
    - trigger: state
      entity_id:
        - sensor.one
        - sensor.two
        - sensor.three
```
## Disabling a trigger
Every individual trigger in an automation can be disabled, without removing it. To do so, add enabled: false to the trigger. For example:

Example script with a disabled trigger
```yaml
automation:
  triggers:
    # This trigger will not trigger, as it is disabled.
    # This automation does not run when the sun is set.
    - enabled: false
      trigger: sun
      event: sunset

    # This trigger will fire, as it is not disabled.
    - trigger: time
      at: "15:32:00"
```
Triggers can also be disabled based on limited templates or blueprint inputs. These are only evaluated once when the automation is loaded.
```yaml
blueprint:
  input:
    input_boolean:
      name: Boolean
      selector:
        boolean:
    input_number:
      name: Number
      selector:
        number:
          min: 0
          max: 100

  trigger_variables:
    _enable_number: !input input_number

  triggers:
    - trigger: sun
      event_type: sunrise
      enabled: !input input_boolean
    - trigger: sun
      event_type: sunset
      enabled: "{{ _enable_number < 50 }}"
```
## Merging lists of triggers
This feature requires Home Assistant version 2024.10 or later. If using this in a blueprint, set the min_version for the blueprint to at least this version.

In some advanced cases (like for blueprints with trigger selectors), it may be necessary to insert a second list of triggers into the main trigger list. This can be done by adding a dictionary in the main trigger list with the sole key triggers, and the value for that key contains a second list of triggers. These will then be flattened into a single list of triggers. For example:
```yaml
blueprint:
  name: Nested Trigger Blueprint
  domain: automation
  input:
    usertrigger:
      selector:
        trigger:

triggers:
  - trigger: event
    event_type: manual_event
  - triggers: !input usertrigger
```
This blueprint automation can then be triggered either by the fixed manual_event trigger, or additionally by any triggers selected in the trigger selector. This is also applicable for wait_for_trigger action.


# Automation Condition
Conditions are an optional part of an automation rule. They can be used to prevent the automation’s actions from being run. After a trigger occurred, all conditions will be checked. If any of them do not return true, the automation will stop executing.

Conditions look very similar to triggers, but they are very different — a trigger will look at events happening in the system, while a condition only looks at how the system looks right now. A trigger can observe that a switch is being turned on. A condition can only see if a switch is currently on or off.

The available conditions for an automation are the same as for the script syntax so see that page for a full list of available conditions.

Example of using condition:
```yaml
automation:
  - alias: "Turn on office lights"
    triggers:
      - trigger: state
        entity_id: sensor.office_motion_sensor
        to: "on"
    conditions:
      - or:
        - condition: numeric_state
          entity_id: sun.sun
          attribute: elevation
          below: 4
        - condition: numeric_state
          entity_id: sensor.office_lux_sensor
          below: 10
    actions:
      - action: scene.turn_on
        target:
          entity_id: scene.office_lights
```
The condition option of an automation, also accepts a single condition template directly. For example:
```yaml
automation:
  - alias: "Turn on office lights"
    triggers:
      - trigger: state
        entity_id: sensor.office_motion_sensor
        to: "on"
    conditions: "{{ state_attr('sun.sun', 'elevation') < 4 }}"
    actions:
      - action: scene.turn_on
        target:
          entity_id: scene.office_lights
```


# Automation Action
The action of an automation rule is what is being executed when a rule fires. The action part follows the script syntax which can be used to interact with anything via other actions or events.

For actions, you can specify the entity_id that it should apply to and optional parameters (to specify for example the brightness).

You can also perform the action to activate a scene which will allow you to define how you want your devices to be and have Home Assistant perform the right action.
```yaml
automation:
  # Change the light in the kitchen and living room to 150 brightness and color red.
  triggers:
    - trigger: sun
      event: sunset
  actions:
    - action: light.turn_on
      target:
        entity_id:
          - light.kitchen
          - light.living_room
      data:
        brightness: 150
        rgb_color: [255, 0, 0]

automation 2:
  # Notify me on my mobile phone of an event
  triggers:
    - trigger: sun
      event: sunset
      offset: -00:30
  variables:
    notification_action: notify.paulus_iphone
  actions:
    # Actions are scripts so can also be a list of actions
    - action: "{{ notification_action }}"
      data:
        message: "Beautiful sunset!"
    - delay: 0:35
    - action: notify.notify
      data:
        message: "Oh wow you really missed something great."
```
Conditions can also be part of an action. You can combine multiple actions and conditions in a single action, and they will be processed in the order you put them in. If the result of a condition is false, the action will stop there so any action after that condition will not be executed.
```yaml
automation:
- alias: "Office at evening"
  triggers:
    - trigger: state
      entity_id: sensor.office_occupancy
      to: "on"
  actions:
    - action: notify.notify
      data:
        message: "Testing conditional actions"
    - condition: or
      conditions:
        - condition: numeric_state
          entity_id: sun.sun
          attribute: elevation
          below: 4
        - condition: state
          entity_id: sensor.office_illuminance
          below: 10
    - action: scene.turn_on
      target:
        entity_id: scene.office_at_evening
```


# Automation Run modes
An automation can be triggered while it is already running.

The automation’s mode configuration option controls what happens when the automation is triggered while the actions are still running from a previous trigger.

Mode	Description
single	(Default) Do not start a new run. Issue a warning.
restart	Start a new run after first stopping the previous run. The automation only restarts if the conditions are met.
queued	Start a new run after all previous runs complete. Runs are guaranteed to execute in the order they were queued. Note that subsequent queued automations will only join the queue if any conditions it may have are met at the time it is triggered.
parallel	Start a new, independent run in parallel with previous runs.

For both queued and parallel modes, configuration option max controls the maximum number of runs that can be executing and/or queued up at a time. The default is 10.

When max is exceeded (which is effectively 1 for single mode) a log message will be emitted to indicate this has happened. Configuration option max_exceeded controls the severity level of that log message. Set it to silent to ignore warnings or set it to a log level. The default is warning.

### Example throttled automation
Some automations you only want to run every 5 minutes. This can be achieved using the single mode and silencing the warnings when the automation is triggered while it’s running.
```yaml
automation:
  - mode: single
    max_exceeded: silent
    triggers:
      - ...
    actions:
      - ...
      - delay: 300  # seconds (=5 minutes)
```
### Example queued
Sometimes an automation is doing an action on a device that does not support multiple simultaneous actions. In such cases, a queue can be used. In that case, the automation will be executed once it’s current invocation and queue are done.
```yaml
automation:
  - mode: queued
    max: 25
    triggers:
      - ...
    actions:
      - ...
```


# Automation action
The automation integration has actions to control automations, like turning automations on and off. This can be useful if you want to disable an automation from another automation.

## Action automation.turn_on
This action enables the automation’s triggers.

Data attribute	Optional	Description
entity_id	no	Entity ID of automation to turn on. Can be a list. none or all are also accepted.

## Action automation.turn_off
This action disables the automation’s triggers, and optionally stops any currently active actions.

Data attribute	Optional	Description
entity_id	no	Entity ID of automation to turn off. Can be a list. none or all are also accepted.
stop_actions	yes	Stop any currently active actions (defaults to true).

## Action automation.toggle
This action enables the automation’s triggers if they were disabled, or disables the automation’s triggers, and stops any currently active actions, if the triggers were enabled.

Data attribute	Optional	Description
entity_id	no	Entity ID of automation to turn on. Can be a list. none or all are also accepted.

## Action automation.trigger
This action will trigger the action of an automation. By default it bypasses any conditions, though that can be changed via the skip_condition attribute.

Data attribute	Optional	Description
entity_id	no	Entity ID of automation to trigger. Can be a list. none or all are also accepted.
skip_condition	yes	Whether or not the condition will be skipped (defaults to true).

## Action automation.reload
This action is only required if you create/edit automations in YAML. Automations via the UI do this automatically.

This action reloads all automations, stopping all currently active automation actions.


# Automation trigger variables
Automations support templating in the same way as scripts do. In addition to the Home Assistant template extensions available to scripts, the trigger and this template variables are available.

The template variable this is also available when evaluating any trigger_variables declared in the configuration.

## Available this data
The variable this is the state object of the automation at the moment of triggering the actions. State objects also contain context data which can be used to identify the user that caused a script or automation to execute. Note that this will not change while executing the actions.

## Available trigger data
The variable trigger is an object that contains details about which trigger triggered the automation.

Templates can use the data to modify the actions performed by the automation or displayed in a message. For example, you could create an automation that multiple sensors can trigger and then use the sensor’s location to specify a light to activate; or you could send a notification containing the friendly name of the sensor that triggered it.

Each trigger platform can include additional data specific to that platform.

### All
Triggers from all platforms will include the following data.

Template variable	Data
trigger.id	The id of the trigger.
trigger.idx	Index of the trigger. (The first trigger idx is 0.)

### Calendar
These are the properties available for a Calendar trigger.

Template variable	Data
trigger.platform	Hardcoded: calendar
trigger.event	The trigger event type, either start or end
trigger.calendar_event	The calendar event object matched.
trigger.calendar_event.summary	The title or summary of the calendar event.
trigger.calendar_event.start	String representation of the start date or date time of the calendar event e.g. 2022-04-10, or 2022-04-10 11:30:00-07:00
trigger.calendar_event.end	String representation of the end time of date time the calendar event in UTC e.g. 2022-04-11, or 2022-04-10 11:45:00-07:00
trigger.calendar_event.all_day	Indicates the event spans the entire day.
trigger.calendar_event.description	A detailed description of the calendar event, if available.
trigger.calendar_event.location	Location information for the calendar event, if available.
trigger.offset	Timedelta object with offset to the event, if any

### Device
These are the properties available for a Device trigger.

Inherites template variables from event or state template based on the type of trigger selected for the device.

Template variable	Data
trigger.platform	Hardcoded: device.

### Event
These are the properties available for a Event trigger.

Template variable	Data
trigger.platform	Hardcoded: event.
trigger.event	Event object that matched.
trigger.event.event_type	Event type.
trigger.event.data	Optional event data.

### Numeric state
These are the properties available for a numeric state trigger.

Template variable	Data
trigger.platform	Hardcoded: numeric_state
trigger.entity_id	Entity ID that we observe.
trigger.below	The below threshold, if any.
trigger.above	The above threshold, if any.
trigger.from_state	The previous state object of the entity.
trigger.to_state	The new state object that triggered trigger.
trigger.for	Timedelta object how long state has met above/below criteria, if any.

### Sentence
These are the properties available for a Sentence trigger.

Template variable	Data
trigger.platform	Hardcoded: conversation
trigger.sentence	Text of the sentence that was matched
trigger.slots	Object with matched slot values
trigger.details	Object with matched slot details by name, such as wildcards. Each detail contains:
name - name of the slot
text - matched text
value - output value (see lists)
trigger.device_id	The device ID that captured the command, if any.

### State
These are the properties available for a State trigger.

Template variable	Data
trigger.platform	Hardcoded: state
trigger.entity_id	Entity ID that we observe.
trigger.from_state	The previous state object of the entity.
trigger.to_state	The new state object that triggered trigger.
trigger.for	Timedelta object how long state has been to state, if any.

### Sun
These are the properties available for a Sun trigger.

Template variable	Data
trigger.platform	Hardcoded: sun
trigger.event	The event that just happened: sunset or sunrise.
trigger.offset	Timedelta object with offset to the event, if any.

### Template
These are the properties available for a Template trigger.

Template variable	Data
trigger.platform	Hardcoded: template
trigger.entity_id	Entity ID that caused change.
trigger.from_state	Previous state object of entity that caused change.
trigger.to_state	New state object of entity that caused template to change.
trigger.for	Timedelta object how long state has been to state, if any.

### Time
These are the properties available for a Time trigger.

Template variable	Data
trigger.platform	Hardcoded: time
trigger.now	DateTime object that triggered the time trigger.

### Time pattern
These are the properties available for a time pattern trigger.

Template variable	Data
trigger.platform	Hardcoded: time_pattern
trigger.now	DateTime object that triggered the time_pattern trigger.

### Persistent notification
These properties are available for a persistent notification trigger.

Template variable	Data
trigger.platform	Hardcoded: persistent_notification
trigger.update_type	Type of persistent notification update added, removed, current, or updated.
trigger.notification	Notification object that triggered the persistent notification trigger.
trigger.notification.notification_id	The notification ID
trigger.notification.title	Title of the notification
trigger.notification.message	Message of the notification
trigger.notification.created_at	DateTime object indicating when the notification was created.

### Webhook
These are the properties available for a Webhook trigger.

Template variable	Data
trigger.platform	Hardcoded: webhook
trigger.webhook_id	The webhook ID that was triggered.
trigger.json	The JSON data of the request (if it had a JSON content type) as a mapping.
trigger.data	The form data of the request (if it had a form data content type).
trigger.query	The URL query parameters of the request (if provided).
### Zone
These are the properties available for a Zone trigger.

Template variable	Data
trigger.platform	Hardcoded: zone
trigger.entity_id	Entity ID that we are observing.
trigger.from_state	Previous state object of the entity.
trigger.to_state	New state object of the entity.
trigger.zone	State object of zone
trigger.event	Event that trigger observed: enter or leave.

* Example configuration.yaml entries
```yaml
automation:
  triggers:
    - trigger: state
      entity_id: device_tracker.paulus
      id: paulus_device
  actions:
    - action: notify.notify
      data:
        message: >
          Paulus just changed from {{ trigger.from_state.state }}
          to {{ trigger.to_state.state }}

          This was triggered by {{ trigger.id }}

automation 2:
  triggers:
    - trigger: mqtt
      topic: "/notify/+"
  actions:
    - action: >
        notify.{{ trigger.topic.split('/')[-1] }}
      data:
        message: "{{ trigger.payload }}"

automation 3:
  triggers:
    # Multiple entities for which you want to perform the same action.
    - trigger: state
      entity_id:
        - light.bedroom_closet
        - light.kiddos_closet
        - light.linen_closet
      to: "on"
      # Trigger when someone leaves one of those lights on for 10 minutes.
      for: "00:10:00"
  actions:
    - action: light.turn_off
      target:
        # Turn off whichever entity triggered the automation.
        entity_id: "{{ trigger.entity_id }}"

automation 4:
  triggers:
    # When an NFC tag is scanned by Home Assistant...
    - trigger: event
      event_type: tag_scanned
      # ...By certain people
      context:
        user_id:
          - 06cbf6deafc54cf0b2ffa49552a396ba
          - 2df8a2a6e0be4d5d962aad2d39ed4c9c
  conditions:
    # Check NFC tag (ID) is the one by the front door
    - condition: template
      value_template: "{{ trigger.event.data.tag_id == '8b6d6755-b4d5-4c23-818b-cf224d221ab7'}}"
  actions:
    # Turn off various lights
    - action: light.turn_off
      target:
        entity_id:
          - light.kitchen
          - light.bedroom
          - light.living_room
```


# Automation YAML
Automations are created in Home Assistant via the UI, but are stored in a YAML format. If you want to edit the YAML of an automation, select the automation, click on the menu button in the top right then on Edit in YAML.

The UI will write your automations to automations.yaml. This file is managed by the UI and should not be edited manually.

It is also possible to write your automations directly inside configuration.yaml or other YAML files. You can do this by adding a labeled automation block to your configuration.yaml:

# The configuration required for the UI to work
automation: !include automations.yaml

# Labeled automation block
automation kitchen:
  - triggers:
      - trigger: ...
YAML
You can add as many labeled automation blocks as you want.

Configuration Variables
Looking for your configuration file?
alias string (Optional)
Friendly name for the automation.

id string (Optional)
A unique id for your automation, will allow you to make changes to the name and entity_id in the UI, and will enable debug traces.

description string (Optional)
A description of the automation.

initial_state boolean (Optional, default: Restored from last run)
Used to define the state of your automation at startup. When not set, the state will be restored from the last run. See Automation initial state.

trace map (Optional, default: {})
Configuration values for the traces stored, currently only stored_traces can be configured.

stored_traces integer (Optional, default: 5)
The number of traces which will be stored. See Number of debug traces stored.

variables map (Optional, default: {})
Variables that will be available inside your templates, both in conditions and actions.

PARAMETER_NAME any
The value of the variable. Any YAML is valid. Templates can also be used to pass a value to the variable.

trigger_variables map (Optional, default: {})
Variables that will be available inside your templates triggers.

PARAMETER_NAME any
The value of the variable. Any YAML is valid. Only limited templates can be used.

mode string (Optional, default: single)
Controls what happens when the automation is invoked while it is still running from one or more previous invocations. See Automation modes.

max integer (Optional, default: 10)
Controls maximum number of runs executing and/or queued up to run at a time. Only valid with modes queued and parallel.

max_exceeded string (Optional, default: warning)
When max is exceeded (which is effectively 1 for single mode) a log message will be emitted to indicate this has happened. This option controls the severity level of that log message. See Log Levels for a list of valid options. Or silent may be specified to suppress the message from being emitted.

triggers list Required
The trigger(s) which will start the automation. Multiple triggers can be added and the automation will start when any of these triggers trigger.

id string (Optional)
An ID that can be used in the automation to determine which trigger caused the automation to start.

variables map (Optional, default: {})
Variables that will be available in the conditions and action sequence.

PARAMETER_NAME any
The value of the variable. Any YAML is valid. Templates can also be used to pass a value to the variable.

conditions list (Optional)
Conditions that have to be true to start the automation. By default all conditions listed have to be true, you can use logical conditions to change this default behavior.

actions list Required
The sequence of actions to be performed in the script.

## Automation modes
Mode	Description
single	Do not start a new run. Issue a warning.
restart	Start a new run after first stopping previous run.
queued	Start a new run after all previous runs complete. Runs are guaranteed to execute in the order they were queued.
parallel	Start a new, independent run in parallel with previous runs.


## YAML example
Example of a YAML based automation that you can add to configuration.yaml.

* Example of entry in configuration.yaml
```yaml
automation my_lights:
  # Turns on lights 1 hour before sunset if people are home
  # and if people get home between 16:00-23:00
  - alias: "Rule 1 Light on in the evening"
    triggers:
      # Prefix the first line of each trigger configuration
      # with a '-' to enter multiple
      - trigger: sun
        event: sunset
        offset: "-01:00:00"
      - trigger: state
        entity_id: all
        to: "home"
    conditions:
      # Prefix the first line of each condition configuration
      # with a '-'' to enter multiple
      - condition: state
        entity_id: all
        state: "home"
      - condition: time
        after: "16:00:00"
        before: "23:00:00"
    actions:
      # With a single action entry, we don't need a '-' before action - though you can if you want to
      - action: homeassistant.turn_on
        target:
          entity_id: group.living_room

  # Turn off lights when everybody leaves the house
  - alias: "Rule 2 - Away Mode"
    triggers:
      - trigger: state
        entity_id: all
        to: "not_home"
    actions:
      - action: light.turn_off
        target:
          entity_id: all

  # Notify when Paulus leaves the house in the evening
  - alias: "Leave Home notification"
    triggers:
      - trigger: zone
        event: leave
        zone: zone.home
        entity_id: device_tracker.paulus
    conditions:
      - condition: time
        after: "20:00"
    actions:
      - action: notify.notify
        data:
          message: "Paulus left the house"

  # Send a notification via Pushover with the event of a Xiaomi cube. Custom event from the Xiaomi integration.
  - alias: "Xiaomi Cube Action"
    initial_state: false
    triggers:
      - trigger: event
        event_type: cube_action
        event_data:
          entity_id: binary_sensor.cube_158d000103a3de
    actions:
      - action: notify.pushover
        data:
          title: "Cube event detected"
          message: "Cube has triggered this event: {{ trigger.event }}"
```
## Extra options
When writing automations directly in YAML, you will have access to advanced options that are not available in the user interface.

### Automation initial state
At startup, automations by default restore their last state of when Home Assistant ran. This can be controlled with the initial_state option. Set it to false or true to force initial state to be off or on.
```yaml
automation:
  - alias: "Automation Name"
    initial_state: false
    triggers:
      - trigger: ...
```
### Number of debug traces stored
When using YAML you can configure the number of debugging traces stored for an automation. This is controlled with the stored_traces option under trace. Set stored_traces to the number of traces you wish to store for the particular automation. If not specified the default value of 5 will be used.
```yaml
automation:
  - alias: "Automation Name"
    trace:
      stored_traces: 10
    triggers:
      - trigger: ...
```
## Migrating your YAML automations to automations.yaml
If you want to migrate your manual automations to use the editor, you’ll have to copy them to automations.yaml. Make sure that automations.yaml remains a list! For each automation that you copy over, you’ll have to add an id. This can be any string as long as it’s unique.

* Example automations.yaml entry. Note, automations.yaml is always a list!
```yaml
- id: my_unique_id  # <-- Required for editor to work, for automations created with the editor the id will be automatically generated.
  alias: "Hello world"
  triggers:
    - trigger: state
      entity_id: sun.sun
      from: below_horizon
      to: above_horizon
  conditions:
    - condition: numeric_state
      entity_id: sensor.temperature
      above: 17
      below: 25
      value_template: "{{ float(state.state) + 2 }}"
  actions:
    - action: light.turn_on
```
## Deleting automations
When automations remain visible in the Home Assistant dashboard, even after having deleted in the YAML file, you have to delete them in the UI.

To delete them completely, go to UI Settings > Devices & services > Entities and find the automation in the search field or by scrolling down.

Check the square box aside of the automation you wish to delete and from the top-right of your screen, select ‘REMOVE SELECTED’.

