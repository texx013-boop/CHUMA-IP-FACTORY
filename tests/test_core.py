import tempfile, pathlib
from chuma_ip_factory import CHUMA

def app():
    d=tempfile.TemporaryDirectory(); c=CHUMA(pathlib.Path(d.name)/'db.sqlite',pathlib.Path(d.name)/'media')
    cleanup=d.cleanup
    def close_and_cleanup():
        c.store.close()
        cleanup()
    d.cleanup=close_and_cleanup
    return d,c

def test_owner_and_character_isolation():
    d,c=app(); o1=c.owner(); o2=c.owner(); cid=c.create_character(o1,'A')
    try: c.status(o2); assert False
    except Exception: pass
    assert c.store.one('SELECT owner_id FROM characters WHERE character_id=?',(cid,))['owner_id']==o1; d.cleanup()

def test_autonomous_growth_cycle():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'A'); r=c.autonomous_cycle(o,cid); assert r['content_id'].startswith('CNT-'); assert r['metrics']['is_test_fixture']; assert c.store.one('SELECT status FROM publications WHERE publication_id=?',(r['publication_id'],))['status']=='PUBLISHED'; d.cleanup()

def test_assembly_first():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'A'); c.initialize_character(o,cid); cid2=c.create_content(o,cid); row=c.store.one('SELECT production_json FROM content WHERE content_id=?',(cid2,)); assert 'ASSEMBLY' in row['production_json']; d.cleanup()

def test_qc_gate_and_publication_boundary():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'A'); c.initialize_character(o,cid); cnt=c.create_content(o,cid)
    try: c.authorize_publish(o,cnt,'x'); assert False
    except Exception: pass
    assert c.qc(o,cnt)=='READY'; p=c.authorize_publish(o,cnt,'x'); assert c.publish(o,p).startswith('test-x-'); d.cleanup()

def test_idempotent_publication_authorization():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'A'); c.initialize_character(o,cid); cnt=c.create_content(o,cid); c.qc(o,cnt); p1=c.authorize_publish(o,cnt,'x'); p2=c.authorize_publish(o,cnt,'x'); assert p1==p2; d.cleanup()

def test_metrics_learning_decision():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'A'); r=c.autonomous_cycle(o,cid); assert c.store.one('SELECT COUNT(*) n FROM signals WHERE owner_id=?',(o,))['n']==2; assert c.store.one('SELECT COUNT(*) n FROM decisions WHERE owner_id=?',(o,))['n']==1; assert c.store.one('SELECT state FROM characters WHERE character_id=?',(cid,))['state'] in ('DISCOVERY','FORMATION'); d.cleanup()

def test_restart_persistence():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'A'); path=c.store.path; c.store.close(); c2=CHUMA(path,path.parent/'media'); assert c2.status(o)['characters']==1; assert c2.store.one('SELECT name FROM characters WHERE character_id=?',(cid,))['name']=='A'; c2.store.close(); d.cleanup()

def test_provenance():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'A'); c.initialize_character(o,cid); cnt=c.create_content(o,cid); p=c.store.one('SELECT provenance_json FROM content WHERE content_id=?',(cnt,)); assert 'schema_version' in p['provenance_json']; d.cleanup()

def test_real_local_image_artifact_and_variants():
    import pathlib, tempfile
    d,c=app(); o=c.owner(); cid=c.create_character(o,'Artifact'); c.initialize_character(o,cid)
    cnt=c.create_content(o,cid,{'mechanic':'portrait','hook':'signature'})
    brief=c.store.one('SELECT brief_json FROM image_briefs WHERE content_id=?',(cnt,))
    assert brief and 'signature' in brief['brief_json']
    arts=c.store.q('SELECT * FROM artifacts WHERE owner_id=? AND asset_id IN (SELECT asset_id FROM assets WHERE owner_id=?)',(o,o))
    assert arts and pathlib.Path(arts[0]['storage_path']).exists()
    variants=c.produce_variants(o,cnt); assert len(variants)==3
    assert c.store.one('SELECT COUNT(*) n FROM artifacts WHERE content_id=?',(cnt,))['n']==3
    d.cleanup()

def test_http_provider_requires_connection():
    from chuma_ip_factory.core import HTTPImageProvider, ProviderNotConnected
    p=HTTPImageProvider()
    assert not p.connected
    try: p.generate({})
    except ProviderNotConnected: pass
    else: assert False

def test_character_initialization_is_idempotent():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'Repeat')
    first=c.initialize_character(o,cid); counts1=(c.store.one('SELECT COUNT(*) n FROM assets WHERE character_id=?',(cid,))['n'], c.store.one('SELECT COUNT(*) n FROM experiments WHERE character_id=?',(cid,))['n'])
    second=c.initialize_character(o,cid); counts2=(c.store.one('SELECT COUNT(*) n FROM assets WHERE character_id=?',(cid,))['n'], c.store.one('SELECT COUNT(*) n FROM experiments WHERE character_id=?',(cid,))['n'])
    assert counts1==counts2==(4,3); assert first['assets_created']==4; assert second['assets_created']==0; d.cleanup()

def test_variants_are_idempotent():
    d,c=app(); o=c.owner(); cid=c.create_character(o,'Variants'); c.initialize_character(o,cid); cnt=c.create_content(o,cid); c.qc(o,cnt)
    a=c.produce_variants(o,cnt); b=c.produce_variants(o,cnt)
    assert a==b and len(a)==3; assert c.store.one('SELECT COUNT(*) n FROM artifacts WHERE content_id=?',(cnt,))['n']==3; d.cleanup()


def test_failed_image_provider_run_is_persisted():
    from chuma_ip_factory.core import ImageProvider
    class FailingProvider(ImageProvider):
        name='failing-test-image'
        def generate(self, request):
            raise RuntimeError('simulated_provider_failure')
    d,cx=app(); cx.image_provider=FailingProvider(); o=cx.owner(); cid=cx.create_character(o,'Failure')
    try:
        cx.initialize_character(o,cid)
        assert False
    except RuntimeError:
        pass
    run=cx.store.one("SELECT status,provider,response_json FROM provider_runs WHERE owner_id=? ORDER BY created_at DESC LIMIT 1",(o,))
    assert run['status']=='FAILED'
    assert run['provider']=='failing-test-image'
    assert 'simulated_provider_failure' in run['response_json']
    d.cleanup()


def test_growth_plan_and_experiment_direction_persist():
    d,cx=app(); o=cx.owner(); cid=cx.create_character(o,'Guided')
    profile=cx.update_character_preferences(o,cid,{'growth_plan':{'direction':'История и личность + Визуальный IP','brief':'Хочу найти сильный образ','mode':'owner-guided'}})
    assert profile['card']['user_controls']['growth_plan']['direction']=='История и личность + Визуальный IP'
    r=cx.autonomous_cycle(o,cid,idea={'mechanic':'discovery_visual','hook':'образ','direction':'Визуальный IP','brief':'образ'})
    row=cx.store.one('SELECT idea_json FROM content WHERE content_id=?',(r['content_id'],))
    assert 'Визуальный IP' in row['idea_json']
    d.cleanup()


def test_reference_upload_is_persisted_and_owned():
    d,cx=app(); o=cx.owner(); cid=cx.create_character(o,'Reference')
    data=b'fake-image-bytes'
    result=cx.attach_reference(o,cid,data,'image/png','reference.png')
    assert result['character_id']==cid
    assert result['size_bytes']==len(data)
    row=cx.store.one('SELECT kind,status,sha256 FROM assets WHERE asset_id=?',(result['asset_id'],))
    assert row['kind']=='REFERENCE' and row['status']=='APPROVED'
    assert row['sha256']
    art=cx.store.one('SELECT variant,status,storage_path FROM artifacts WHERE artifact_id=?',(result['artifact_id'],))
    assert art['variant']=='reference' and art['status']=='READY'
    assert pathlib.Path(art['storage_path']).exists()
    profile=cx.character_profile(o,cid)
    assert profile['card']['reference_asset_id']==result['asset_id']
    d.cleanup()


def test_growth_recommendation_is_evidence_based():
    d,cx=app(); o=cx.owner(); cid=cx.create_character(o,'Growth')
    for direction in ('История и личность','Визуальный IP','История и личность'):
        r=cx.autonomous_cycle(o,cid,idea={'mechanic':'discovery_story','hook':direction,'direction':direction,'brief':direction})
        assert r['metrics']['is_test_fixture']
    rec=cx.growth_recommendation(o,cid)
    assert rec['stage']=='FORMATION'
    assert rec['recommendation']=='История и личность'
    assert rec['tested']==3
    assert 0 < rec['confidence'] <= 1
    d.cleanup()
