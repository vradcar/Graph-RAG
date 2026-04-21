# GraphRAG Schema Contract — Week 2

**Owner:** Member 1 (Data Ingestion & Schema)
**Consumers:** Member 2 (Cypher/Traversal), Member 4 (Context Assembly)
**Status:** DRAFT — pending Member 2 review
**Source doc:** Honeywell Home T9 Wi-Fi Thermostat Installation Guide (17 pages)

This document is the single source of truth for node types, edge types, and properties in the graph. All Cypher queries, ingestion code, and context assembly must conform. Changes require sign-off from Member 1 and Member 2.

---

## 1. Design goals

- Support **multi-hop** queries required by Week 2 (single-hop vs multi-hop comparison).
- Enable the "modern replacement for discontinued part" query pattern from the project brief.
- Every node and edge carries `source_page` for citation in Stage 4 (Context Assembly).
- Schema must accept additional thermostat models without structural changes.

---

## 2. Node types

Every node has a `type` label, a unique `id`, and a `source_page` pointing back to the PDF page where the entity was defined.

### 2.1 Thermostat

| Property         | Type                                | Required | Example                         |
|------------------|-------------------------------------|----------|---------------------------------|
| `id`             | string (slug)                       | yes      | `t9_rcht9610wf`                 |
| `name`           | string                              | yes      | `Honeywell Home T9 Wi-Fi`       |
| `model_number`   | string                              | yes      | `RCHT9610WF`                    |
| `status`         | enum: `current` \| `discontinued`   | yes      | `current`                       |
| `product_family` | string                              | yes      | `T-Series`                      |
| `wifi`           | boolean                             | yes      | `true`                          |
| `source_page`    | integer                             | yes      | `1`                             |

### 2.2 HVACSystemType

| Property        | Type                                                      | Required | Example            |
|-----------------|-----------------------------------------------------------|----------|--------------------|
| `id`            | string (slug)                                             | yes      | `heat_pump`        |
| `name`          | string                                                    | yes      | `Heat Pump System` |
| `voltage_class` | enum: `low_voltage_24v` \| `line_voltage` \| `millivolt`  | yes      | `low_voltage_24v`  |
| `source_page`   | integer                                                   | yes      | `3`                |

### 2.3 WiringTerminal

| Property      | Type           | Required | Example                       |
|---------------|----------------|----------|-------------------------------|
| `id`          | string (slug)  | yes      | `terminal_c`                  |
| `label`       | string         | yes      | `C`                           |
| `function`    | string         | yes      | `Common wire, 24V AC return`  |
| `source_page` | integer        | yes      | `6`                           |

### 2.4 RoomSensor

| Property       | Type              | Required | Example                                    |
|----------------|-------------------|----------|--------------------------------------------|
| `id`           | string (slug)     | yes      | `wireless_room_sensor`                     |
| `name`         | string            | yes      | `Honeywell Wireless Room Sensor`           |
| `capabilities` | array of strings  | yes      | `["temperature", "humidity", "occupancy"]` |
| `source_page`  | integer           | yes      | `13`                                       |

### 2.5 Adapter

| Property      | Type           | Required | Example           |
|---------------|----------------|----------|-------------------|
| `id`          | string (slug)  | yes      | `c_wire_adapter`  |
| `name`        | string         | yes      | `C-Wire Adapter`  |
| `included`    | boolean        | yes      | `true`            |
| `source_page` | integer        | yes      | `3`               |

### 2.6 ElectricalSpec

| Property       | Type           | Required | Example    |
|----------------|----------------|----------|------------|
| `id`           | string (slug)  | yes      | `t9_power` |
| `voltage_v`    | number         | yes      | `24`       |
| `frequency_hz` | number         | yes      | `60`       |
| `current_a`    | number         | yes      | `0.2`      |
| `source_page`  | integer        | yes      | `3`        |

### 2.7 OperatingRange

| Property      | Type                      | Required | Example          |
|---------------|---------------------------|----------|------------------|
| `id`          | string (slug)             | yes      | `t9_heat_range`  |
| `mode`        | enum: `heat` \| `cool`    | yes      | `heat`           |
| `min_f`       | integer                   | yes      | `40`             |
| `max_f`       | integer                   | yes      | `90`             |
| `source_page` | integer                   | yes      | `16`             |

### 2.8 ZoningPanel

| Property      | Type           | Required | Example                      |
|---------------|----------------|----------|------------------------------|
| `id`          | string (slug)  | yes      | `zoning_panel`               |
| `name`        | string         | yes      | `Zoning Panel Installation`  |
| `source_page` | integer        | yes      | `7`                          |

### 2.9 Wallplate

| Property      | Type           | Required | Example       |
|---------------|----------------|----------|---------------|
| `id`          | string (slug)  | yes      | `uwp`         |
| `name`        | string         | yes      | `UWP Wallplate` |
| `source_page` | integer        | yes      | `2`           |

---

## 3. Edge types

Direction is `(source) -[edge]-> (target)`.

| Edge type                    | Source        | Target          | Edge properties                             | Source page |
|------------------------------|---------------|-----------------|---------------------------------------------|-------------|
| `COMPATIBLE_WITH`            | Thermostat    | HVACSystemType  | —                                           | 3           |
| `NOT_COMPATIBLE_WITH`        | Thermostat    | HVACSystemType  | `reason: string`                            | 3           |
| `REQUIRES`                   | Thermostat    | WiringTerminal  | `required: boolean`                         | 6           |
| `CONNECTS_TO`                | Thermostat    | RoomSensor      | `max_count: int`, `max_range_ft: int`       | 13          |
| `NEEDS_ADAPTER_IF_MISSING`   | Thermostat    | Adapter         | `condition: string`                         | 3, 7        |
| `COMPLEX_ON`                 | Adapter       | ZoningPanel     | `note: string`                              | 7           |
| `HAS_ELECTRICAL_SPEC`        | Thermostat    | ElectricalSpec  | —                                           | 3           |
| `HAS_OPERATING_RANGE`        | Thermostat    | OperatingRange  | —                                           | 16          |
| `MOUNTS_ON`                  | Thermostat    | Wallplate       | —                                           | 10          |
| `REPLACED_BY`                | Thermostat    | Thermostat      | `replacement_date: string` (optional)       | manual data |

**`REPLACED_BY`** is the edge that makes the "modern replacement for discontinued part" query work. It is not present in the T9 PDF alone — it is added by the ingestion layer from a hand-curated `replacements.json` file so discontinued-to-current chains can be traversed. This is the Week 2 expansion beyond the T9-only graph.

---

## 4. ID conventions

- All IDs are lowercase snake_case slugs.
- Thermostat IDs: `<family>_<model_number_lowercase>` → `t9_rcht9610wf`.
- Terminal IDs: `terminal_<label_lowercase>` → `terminal_c`, `terminal_rc`.
- HVAC system type IDs: short canonical name → `heat_pump`, `electric_baseboard`, `millivolt`.
- Every ID is globally unique across node types.

---

## 5. Contract rules for ingestion

1. Loader must be **idempotent**: re-running ingestion on the same input must not duplicate nodes or edges. Use `MERGE` on `id` (Neo4j) or `has_node` check (networkx).
2. Every node and edge inserted must carry `source_page`. Ingestion rejects records without it.
3. Enum values are validated at load time. Unknown `status` or `voltage_class` values fail the load with a clear error.
4. Optional edge properties may be omitted, but required properties must be present.

---

## 6. Example graph walk — multi-hop query support

Query: *"What systems is the T9 not compatible with, and why?"*
Traversal: `(Thermostat {id:'t9_rcht9610wf'}) -[NOT_COMPATIBLE_WITH]-> (HVACSystemType)` — returns both target nodes and the edge `reason` property. 1-hop.

Query: *"Do I need a C-Wire Adapter, and does that matter on a zoning panel?"*
Traversal: `(Thermostat) -[NEEDS_ADAPTER_IF_MISSING]-> (Adapter) -[COMPLEX_ON]-> (ZoningPanel)`. 2-hop.

Query: *"What is the modern replacement for the RTH6580WF?"*
Traversal: `(Thermostat {status:'discontinued'}) -[REPLACED_BY]-> (Thermostat {status:'current'})`. 1-hop, but requires the curated replacement data.

Query: *"What are the capabilities of the sensor that connects to the T9?"*
Traversal: `(Thermostat) -[CONNECTS_TO]-> (RoomSensor)` → read `capabilities` property. 1-hop with property read.

---

## 7. Changelog

- **v0.1** (Week 2, Day 1): Initial schema. Draft pending Member 2 review.
