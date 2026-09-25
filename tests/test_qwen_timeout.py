"""Guard the actual DashScope request timeout keyword; no provider calls."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from vconflict_pipeline import qa

class QwenTimeoutTests(unittest.TestCase):
    def test_pipeline_timeout_reaches_sdk_transport_keyword(self):
        sdk=SimpleNamespace(MultiModalConversation=SimpleNamespace(call=Mock(return_value={})))
        with patch.object(qa,'_require_dashscope_sdk',return_value=sdk), \
             patch.object(qa,'_dashscope_base_http_api_url',return_value='https://example.invalid/api/v1'), \
             patch.object(qa,'_normalize_dashscope_response',return_value={'ok':True}):
            result=qa._send_qwen_request(prompt_text='What is the resulting list?',
                video_uri='file:///tmp/test.mp4',thinking_effort='default',api_key='offline',timeout=17)
        sent=sdk.MultiModalConversation.call.call_args.kwargs
        self.assertEqual(sent['request_timeout'],17)
        self.assertNotIn('timeout',sent)
        self.assertEqual(result,{'ok':True})

if __name__=='__main__':unittest.main()
