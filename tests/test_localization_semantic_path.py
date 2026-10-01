import unittest
from scripts.localization_semantic_path import resolve_semantic_path
from scripts.sync_localization_structure import merge_structure

class SemanticPathTests(unittest.TestCase):
    def test_reordered_identity(self):
        document={'dataList':[{'id':2,'name':'other'},{'id':1,'name':'target'}]}
        self.assertEqual(resolve_semantic_path(document,['dataList','@id=1','name']),['dataList',1,'name'])

    def test_duplicate_identity_with_position(self):
        document={'dataList':[{'id':1,'texts':[{'id':0,'text':'a'},{'id':0,'text':'b'}]}]}
        self.assertEqual(resolve_semantic_path(document,['dataList','@id=1','texts','@id=0#1','text']),['dataList',0,'texts',1,'text'])

    def test_ambiguous_identity_rejected(self):
        with self.assertRaises(ValueError):
            resolve_semantic_path([{'id':1},{'id':1}],['@id=1'])

    def test_insert_in_list_with_duplicate_ids_preserves_translations(self):
        en=[{'key':'new','text':'new'},{'key':'a','text':'one'},
            {'key':'a','text':'two'},{'key':'b','text':'three'}]
        ru=[{'key':'a','text':'один'},{'key':'a','text':'два'},{'key':'b','text':'три'}]
        result=merge_structure(en,ru)
        self.assertEqual([r['text'] for r in result],['new','один','два','три'])

if __name__=='__main__':unittest.main()
