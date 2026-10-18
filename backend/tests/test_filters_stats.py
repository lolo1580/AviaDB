"""Filtres, recherche, tri, statistiques et facettes."""

from __future__ import annotations

import pytest


@pytest.fixture
def collection(create_item):
    """Jeu de données de référence (5 objets)."""
    return {
        "rafale": create_item(
            name="Rafale M 11F Tiger Meet 2024", country="France", aircraft_model="Rafale M",
            status="EXHIBITED", estimated_value=120, purchase_price=89.9,
            purchase_date="2024-05-01", tags=["Tiger Meet", "Marine"],
            diecast={"scale": "1/72", "manufacturer": "Hobby Master", "part_number": "HA6501"},
        ),
        "f16": create_item(
            name="F-16AM Solo Display", country="Netherlands", aircraft_model="F-16AM",
            status="STORED_BOX", estimated_value=45, tags=["Solo Display"],
            diecast={"scale": "1/72", "manufacturer": "JC Wings"},
        ),
        "f35": create_item(
            name="F-35A 313th Squadron", country="Netherlands", aircraft_model="F-35A",
            status="TRANSIT", estimated_value=60, purchase_date="2025-02-01",
            diecast={"scale": "1/48", "manufacturer": "Hobby Master"},
        ),
        "patch11f": create_item(
            name="Patch Flottille 11F", item_type="PATCH", country="France",
            status="STORED_BOX", estimated_value=15, tags=["Tiger Meet"],
            patch={"unit_squadron": "Flottille 11F", "base": "BAN Landivisiau",
                   "material": "EMBROIDERED"},
        ),
        "patch313": create_item(
            name="Patch 313th Squadron", item_type="PATCH", country="Netherlands",
            status="EXHIBITED", estimated_value=25,
            patch={"unit_squadron": "313th Squadron", "material": "PVC"},
        ),
    }


def ids_of(response):
    return sorted(item["id"] for item in response.json()["items"])


def test_text_search_covers_details(admin_client, collection):
    assert ids_of(admin_client.get("/api/items", params={"q": "rafale"})) == [collection["rafale"]["id"]]
    assert ids_of(admin_client.get("/api/items", params={"q": "Landivisiau"})) == [collection["patch11f"]["id"]]
    assert ids_of(admin_client.get("/api/items", params={"q": "HA6501"})) == [collection["rafale"]["id"]]


def test_single_value_filters(admin_client, collection):
    assert ids_of(admin_client.get("/api/items", params={"item_type": "DIECAST"})) == sorted(
        [collection["rafale"]["id"], collection["f16"]["id"], collection["f35"]["id"]]
    )
    assert ids_of(admin_client.get("/api/items", params={"status": "STORED_BOX"})) == sorted(
        [collection["f16"]["id"], collection["patch11f"]["id"]]
    )
    assert ids_of(admin_client.get("/api/items", params={"scale": "1/72"})) == sorted(
        [collection["rafale"]["id"], collection["f16"]["id"]]
    )
    assert ids_of(admin_client.get("/api/items", params={"manufacturer": "Hobby Master"})) == sorted(
        [collection["rafale"]["id"], collection["f35"]["id"]]
    )


def test_multi_value_and_tag_filters_use_or(admin_client, collection):
    assert len(ids_of(admin_client.get("/api/items", params=[("item_type", "DIECAST"), ("item_type", "PATCH")]))) == 5
    assert ids_of(admin_client.get("/api/items", params=[("tag", "Tiger Meet")])) == sorted(
        [collection["rafale"]["id"], collection["patch11f"]["id"]]
    )
    assert len(ids_of(admin_client.get("/api/items", params=[("tag", "Tiger Meet"), ("tag", "Solo Display")]))) == 3


def test_value_range_and_combined_filters(admin_client, collection):
    assert ids_of(admin_client.get("/api/items", params={"value_min": 60})) == sorted(
        [collection["rafale"]["id"], collection["f35"]["id"]]
    )
    assert ids_of(admin_client.get("/api/items", params={"value_max": 25})) == sorted(
        [collection["patch11f"]["id"], collection["patch313"]["id"]]
    )
    assert ids_of(
        admin_client.get("/api/items", params={"item_type": "DIECAST", "country": "France"})
    ) == [collection["rafale"]["id"]]


def test_has_loan_filter(admin_client, collection):
    admin_client.patch(
        f"/api/items/{collection['f16']['id']}", json={"loaned_to": "Club aéro"}
    )
    borrowed = admin_client.get("/api/items", params={"has_loan": True}).json()["items"]
    assert [item["id"] for item in borrowed] == [collection["f16"]["id"]]
    assert admin_client.get("/api/items", params={"has_loan": False}).json()["total"] == 4


def test_sorting_and_pagination(admin_client, collection):
    descending = admin_client.get("/api/items", params={"sort": "estimated_value", "order": "desc"}).json()
    assert descending["items"][0]["id"] == collection["rafale"]["id"]

    page = admin_client.get("/api/items", params={"limit": 2}).json()
    assert page["total"] == 5 and len(page["items"]) == 2

    filtered = admin_client.get("/api/items", params={"country": "France", "limit": 1}).json()
    assert filtered["total"] == 2


def test_invalid_parameters_are_rejected(admin_client):
    assert admin_client.get("/api/items", params={"sort": "bogus"}).status_code == 422
    assert admin_client.get("/api/items", params={"status": "BOGUS"}).status_code == 422


def test_stats_totals_and_breakdowns(admin_client, collection):
    stats = admin_client.get("/api/stats").json()
    assert stats["total_items"] == 5
    assert stats["total_estimated_value"] == pytest.approx(265.0)
    assert stats["total_purchase_value"] == pytest.approx(89.9)

    assert {b["key"]: b["count"] for b in stats["by_type"]} == {"DIECAST": 3, "PATCH": 2}
    assert {b["key"]: b["count"] for b in stats["by_country"]} == {"Netherlands": 3, "France": 2}
    assert {b["key"]: b["count"] for b in stats["by_scale"]} == {"1/72": 2, "1/48": 1}
    assert {b["key"]: b["count"] for b in stats["by_material"]} == {"EMBROIDERED": 1, "PVC": 1}
    assert {b["key"]: b["count"] for b in stats["by_year"]} == {"2024": 1, "2025": 1}

    value_by_country = {b["key"]: b["value"] for b in stats["value_by_country"]}
    assert value_by_country["France"] == pytest.approx(135.0)
    assert value_by_country["Netherlands"] == pytest.approx(130.0)


def test_facets_list_distinct_values(admin_client, collection):
    facets = admin_client.get("/api/meta/facets").json()
    assert facets["countries"] == ["France", "Netherlands"]
    assert facets["scales"] == ["1/48", "1/72"]
    assert facets["manufacturers"] == ["Hobby Master", "JC Wings"]
    assert facets["tags"] == ["Marine", "Solo Display", "Tiger Meet"]
