def test_clean_routes_reload_and_unknown_paths(client):
    for path in ('/','/about','/bookmarks','/progress','/admin','/admin/login','/paper/42','/course/1','/attempt/7','/result/7','/exam/Quiz%201'):
        response=client.get(path)
        assert response.status_code==200,path
        assert '<div id="app">' in response.text
    assert client.get('/unknown-page').status_code==404
    assert client.get('/assets/missing.js').status_code==404
    assert client.get('/api/not-a-real-endpoint').status_code==404
