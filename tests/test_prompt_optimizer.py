import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json
import yaml
import shutil
import dotenv

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.abspath(os.path.join(script_dir, '../.env')))
sys.path.append(os.path.abspath(os.path.join(script_dir, '../scripts')))

import agent_healer
from agent_healer import (
    get_current_system_prompt,
    update_litellm_config_prompt,
    optimize_prompt_with_dify_or_sdk,
    detect_prompt_error,
    PromptFixProposal
)

class TestPromptOptimizer(unittest.TestCase):
    def setUp(self):
        # 一時テスト用の litellm_config.yaml を作成
        self.repo_root = os.path.abspath(os.path.join(script_dir, '..'))
        self.temp_config = os.path.join(self.repo_root, "litellm_config.yaml.test")
        
        # テスト設定データ
        self.mock_config_data = {
            "model_list": [
                {
                    "model_name": "gemini-3.5-flash",
                    "litellm_params": {
                        "model": "gemini/gemini-3.5-flash",
                        "system_prompt": "Original prompt for flash"
                    }
                },
                {
                    "model_name": "qwen2.5-coder",
                    "litellm_params": {
                        "model": "ollama/qwen2.5-coder",
                        "system_prompt": "Original prompt for qwen"
                    }
                }
            ]
        }
        with open(self.temp_config, 'w', encoding='utf-8') as f:
            yaml.safe_dump(self.mock_config_data, f)

        # agent_healerの対象パスを一時ファイルに差し替え（本物の破壊を防ぐ）
        self.real_config_path = agent_healer.LITELLM_CONFIG_PATH
        agent_healer.LITELLM_CONFIG_PATH = self.temp_config
        
    def tearDown(self):
        # パスを元に戻す
        agent_healer.LITELLM_CONFIG_PATH = self.real_config_path
        if os.path.exists(self.temp_config):
            os.remove(self.temp_config)

    def test_get_current_prompt_real(self):
        """Test prompt loader retrieves correct initial prompt from file"""
        prompt = agent_healer.get_current_system_prompt("gemini-3.5-flash")
        self.assertEqual(prompt, "Original prompt for flash")
        
        prompt_qwen = agent_healer.get_current_system_prompt("qwen2.5-coder")
        self.assertEqual(prompt_qwen, "Original prompt for qwen")

    def test_update_config_prompt_real(self):
        """Test config prompt updates successfully in file"""
        success = agent_healer.update_litellm_config_prompt("gemini-3.5-flash", "New optimized prompt instructions")
        self.assertTrue(success)
        
        # 実際に一時ファイルのプロンプト指示が更新されたことを検証
        updated_prompt = agent_healer.get_current_system_prompt("gemini-3.5-flash")
        self.assertEqual(updated_prompt, "New optimized prompt instructions")

    def test_detect_prompt_error_variants(self):
        """Test detection of formatting and parser errors in logs"""
        xml_err = "2026-06-29 21:00:00 - ERROR - XML parsing failed: Root element missing."
        json_err = "2026-06-29 21:00:00 - ERROR - Invalid JSON format: unexpected token."
        no_tags = "2026-06-29 21:00:00 - WARNING - Output must contain XML tags like <action> but none found."
        clean_log = "2026-06-29 21:00:00 - INFO - Successfully uploaded document."
        
        self.assertTrue(detect_prompt_error(xml_err))
        self.assertTrue(detect_prompt_error(json_err))
        self.assertTrue(detect_prompt_error(no_tags))
        self.assertFalse(detect_prompt_error(clean_log))

    @patch('requests.post')
    def test_optimize_prompt_with_dify_workflow_api(self, mock_post):
        """Test optimize_prompt uses Dify Workflow API when key is present"""
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {
            "data": {
                "outputs": {
                    "optimized_prompt": "Dify workflow optimized system instructions",
                    "explanation": "Added XML enforcement rule"
                }
            }
        }
        mock_post.return_value = mock_res
        
        env = {
            "DIFY_WORKFLOW_API_KEY": "mock-workflow-api-key",
            "DIFY_WORKFLOW_API_BASE": "http://mock-dify/v1"
        }
        
        import asyncio
        with patch.dict(os.environ, env):
            async def run_test():
                proposal = await optimize_prompt_with_dify_or_sdk(
                    "Current prompt", "XML parsing failed", "gemini-3.5-flash"
                )
                self.assertIsNotNone(proposal)
                self.assertEqual(proposal.optimized_prompt, "Dify workflow optimized system instructions")
                self.assertEqual(proposal.explanation, "Added XML enforcement rule")
                
            asyncio.run(run_test())
            mock_post.assert_called_once()

if __name__ == '__main__':
    unittest.main()
