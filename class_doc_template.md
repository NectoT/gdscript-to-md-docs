{% macro definition_args(args) %}
    {%- for arg in args -%}
        {{arg.name}}
        {%- if arg.type is not none -%}
            : `{{arg.type}}`
        {%- endif -%}
        {%- if arg.default is not none -%}
            {{" "}}= {{arg.default}}
        {%- endif -%}
        {{", " if not loop.last else ""}}
    {%- endfor -%}
{%- endmacro -%}

{# If you want to have a name header, uncomment this line:
# {{name}}
#}

`{{file_path}}`

*extends `{{extends}}`*

___ 

{% if summary is not none %}
**{{summary}}**
{% endif %}

{% if description is not none %}
## Description

{{description}}
{% endif %}

{% if signals|length != 0 %}
## Signals

{% for signal in signals|sort(attribute='name') %}
{% if signal.args|length != 0 %}
### {{signal.name}}({{definition_args(signal.args)}})
{% else %}
### {{signal.name}}
{% endif %}

{{signal.description if signal.description is not none else ""}}
{% endfor %}
{% endif %}

{% if enums|length != 0 %}
## Enums

{% for enum in enums|sort(attribute='name') %}
### {{enum.name}}:

{{- enum.description if enum.description else "" }}

{% for value in enum.vals %}
- **{{value}}**

{{ enum.vals[value] if enum.vals[value] else "" }}

{% endfor %}

{% endfor %}
{% endif %}

{% if properties|length != 0 %}
## Properties

{% for property in properties|sort(attribute='name') %}
### `{{property.type if property.type else "Variant"}}` {{property.name}}
{%- if property.default is not none -%}
    {{" "}}= {{property.default}}
{% endif %}

{% if property.has_setter %}*has setter* {% endif %}
{% if property.has_setter and property.has_getter %}*,*{% endif %}
{% if property.has_getter %} *has getter*{% endif %}


{{property.description if property.description else ""}}
{% endfor %}
{% endif %}

{% if methods|length != 0 %}
## Methods

{% for method in methods|sort(attribute='name') %}
### `{{method.type if method.type else "void"}}` {{method.name}}({{definition_args(method.args)}})

{{method.description if method.description else ""}}
{% endfor %}
{% endif %}