{#
    Cross-warehouse compatibility macros for ASRE dbt models.
    Handles differences between Postgres, Snowflake, BigQuery, and Redshift.
#}

{# -- Quote an identifier (handles reserved words across warehouses) -- #}
{% macro quote_identifier(identifier) %}
    {% if target.type == 'bigquery' %}
        `{{ identifier }}`
    {%- else %}
        "{{ identifier }}"
    {%- endif %}
{% endmacro %}

{# -- JSON column type: JSONB (Postgres), VARIANT (Snowflake), JSON (BigQuery), SUPER (Redshift) -- #}
{% macro json_type() %}
    {% if target.type == 'snowflake' %}
        VARIANT
    {% elif target.type == 'bigquery' %}
        JSON
    {% elif target.type == 'redshift' %}
        SUPER
    {% else %}
        JSONB
    {% endif %}
{% endmacro %}

{# -- Array column type: JSONB (Postgres), ARRAY (Snowflake), ARRAY<STRING> (BigQuery), SUPER (Redshift) -- #}
{% macro array_type() %}
    {% if target.type == 'snowflake' %}
        ARRAY
    {% elif target.type == 'bigquery' %}
        ARRAY<STRING>
    {% elif target.type == 'redshift' %}
        SUPER
    {% else %}
        JSONB
    {% endif %}
{% endmacro %}

{# -- Timestamp with timezone type -- #}
{% macro timestamp_type() %}
    {% if target.type == 'snowflake' %}
        TIMESTAMP_TZ
    {% elif target.type == 'bigquery' %}
        TIMESTAMP
    {% elif target.type == 'redshift' %}
        TIMESTAMPTZ
    {% else %}
        TIMESTAMPTZ
    {% endif %}
{% endmacro %}

{# -- Current timestamp function -- #}
{% macro current_timestamp_value() %}
    {% if target.type == 'bigquery' %}
        CURRENT_TIMESTAMP()
    {% else %}
        CURRENT_TIMESTAMP
    {% endif %}
{% endmacro %}
