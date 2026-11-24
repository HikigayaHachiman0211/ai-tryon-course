def test_products_resolve_explicit_locale_and_return_display_contract(client) -> None:
    response = client.get(
        "/api/products",
        params={"locale": "en", "limit": 1},
        headers={"Accept-Language": "ja-JP"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["locale"] == "en"
    item = payload["items"][0]
    assert item["product_key"]
    assert item["display"]["title"] == item["title"]
    assert item["display"]["styleType"]
    assert item["canonical"]["price"] == item["price"]
    assert "测试" not in item["display"]["title"]


def test_products_default_to_chinese_for_old_clients(client) -> None:
    response = client.get("/api/products", params={"limit": 1})
    assert response.status_code == 200
    payload = response.json()
    assert payload["locale"] == "zh-CN"
    assert payload["items"][0]["title"].startswith("测试羽绒服")


def test_relocalizing_current_recommendations_preserves_scores_and_order(client) -> None:
    products = client.get('/api/products', params={'locale': 'zh-CN', 'limit': 2}).json()['items']
    for index, product in enumerate(products):
        product['total_score'] = 90 - index
        product['score_breakdown'] = {'颜色适配度': 80, '款式适配度': 70}
    original = {'locale': 'zh-CN', 'items': products, 'inference': {'resolved_style': '短款'}}
    response = client.post('/api/localize-result', json={'kind': 'recommend', 'locale': 'ja', 'result': original})
    assert response.status_code == 200
    result = response.json()
    assert result['locale'] == 'ja'
    assert [item['product_key'] for item in result['items']] == [item['product_key'] for item in products]
    assert [item['total_score'] for item in result['items']] == [90, 89]
    assert sorted(result['items'][0]['score_breakdown'].values()) == [70, 80]
    assert 'ダウンジャケット' in result['items'][0]['title']
