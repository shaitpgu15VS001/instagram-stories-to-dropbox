import json
p='scripts/debug_fastdl_israel.json'
cap=json.load(open(p,'r',encoding='utf-8'))
net=cap.get('network',[])
reqs=sum(1 for e in net if e.get('url') and '/api/v1/instagram/stories' in e.get('url') and e.get('type')=='request')
resps=sum(1 for e in net if e.get('url') and '/api/v1/instagram/stories' in e.get('url') and e.get('type')=='response')
print('requests',reqs,'responses',resps)
