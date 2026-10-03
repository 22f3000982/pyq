import io
from PIL import Image
from conftest import login

def test_public_defaults_and_admin_edits(client):
    assert client.get('/api/about').json['headline']
    guest=login(client)
    assert client.put('/api/admin/about',json={'name':'Ash'},headers=guest).status_code==401
    headers=login(client,admin=True)
    assert client.put('/api/admin/about',json={'name':'Ash'}).status_code==403
    assert client.put('/api/admin/about',json={'name':'Ash','bio':'Hello <script>text</script>'},headers=headers).status_code==200
    assert client.get('/api/about').json['name']=='Ash'
    assert client.put('/api/admin/about',json={'headline':' '},headers=headers).status_code==400
    assert client.put('/api/admin/about',json={'name':'x'*101},headers=headers).status_code==400
    assert client.put('/api/admin/about',json={'photo_url':'evil'},headers=headers).status_code==400

def test_photo_validated_persisted_and_removed(client):
    headers=login(client,admin=True)
    assert client.post('/api/admin/about/photo',data={'photo':(io.BytesIO(b'<svg/>'),'x.svg')},headers=headers).status_code==400
    picture=io.BytesIO();Image.new('RGB',(1000,900),'red').save(picture,'PNG');picture.seek(0)
    assert client.post('/api/admin/about/photo',data={'photo':(picture,'photo.png')},headers=headers).status_code==200
    response=client.get('/api/about/photo')
    assert response.status_code==200 and response.mimetype=='image/jpeg'
    image=Image.open(io.BytesIO(response.data));assert max(image.size)<=800
    assert client.get('/api/about').json['photo_url']=='/api/about/photo'
    assert client.delete('/api/admin/about/photo',headers=headers).status_code==200
    assert client.get('/api/about/photo').status_code==404
