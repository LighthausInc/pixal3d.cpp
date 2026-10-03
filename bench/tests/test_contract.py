import importlib.util, json, pathlib, sys, tempfile, unittest
from unittest.mock import patch
B=pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0,str(B)); import run
class SafetyContract(unittest.TestCase):
    def test_reject_unapproved_repository(self):
        with self.assertRaisesRegex(ValueError,'Unapproved'): run.verified_models({'hf_repo':'attacker/model'})
    def test_reject_mutable_hf_revision(self):
        with self.assertRaisesRegex(ValueError,'revision'): run.verified_models({'hf_repo':'raven38/pixal3d-q8_0-v1','hf_revision':'main'})
    def test_hash_and_path_guard_before_loading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp); weights=root/'weights'; weights.mkdir(); f=weights/'m.gguf'; f.write_bytes(b'good'); manifest=root/'manifest.json'
            base={'name':'m.gguf','size_bytes':4,'sha256':run.sha(f)}; manifest.write_text(json.dumps({'files':[base]}))
            model={'hf_repo':'raven38/pixal3d-test','hf_revision':'a'*40,'weights':str(weights),'manifest':str(manifest)}
            (weights/'manual-verification.json').write_text(json.dumps({'manifest_sha256':run.sha(manifest),'reviewer':'test','evaluation_only':True}))
            self.assertEqual(run.verified_models(model)['files'][0]['actual_sha256'],base['sha256'])
            f.write_bytes(b'evil')
            with self.assertRaisesRegex(ValueError,'SHA-256'): run.verified_models(model)
            base['name']='../m.gguf'; manifest.write_text(json.dumps({'files':[base]}))
            with self.assertRaisesRegex(ValueError,'Unsafe'): run.verified_models(model)
    def test_no_server_command_and_camera_units(self):
        host={'backend':'Metal','engines':{'pixal':{'binary':'../build/trellis-cli'},'trellis':{'binary':'../../trellis.cpp/build/trellis-cli'}}}
        for engine,mode in [('pixal','mv'),('pixal','sv'),('trellis','trellis'),('trellis','pixal')]:
            cmd=run.command({'engine':engine,'mode':mode,'weights':'weights/test'},host,{},1024,42,pathlib.Path('/tmp/cell'))
            self.assertIn('--require-gpu',cmd); self.assertNotIn('trellis-server',' '.join(cmd))
            if mode=='sv': self.assertEqual(cmd[cmd.index('--fov')+1],'0.3490658503988659')
            if mode=='pixal': self.assertEqual(cmd[cmd.index('--fov')+1],'20')
    def test_reference_provenance(self):
        for asset in ['monitor','probe','laryngoscope']:
            rec=run.verified_input({'input':f'inputs/{asset}'})
            self.assertEqual(len(rec['files']),5)
if __name__=='__main__': unittest.main()
