import unittest
from unittest.mock import patch
from network_api import warn_cleanup, ActionRequest
import base64

class TestWarnCleanupUpdate(unittest.TestCase):
    @patch('network_api.execute_ssh_command')
    def test_warn_cleanup_logic_updated(self, mock_ssh):
        mock_ssh.return_value = {"success": True, "output": "Mock Success", "error": ""}
        
        request = ActionRequest(ips=["192.168.1.50"])
        results = warn_cleanup(request)
        
        called_ip, called_command = mock_ssh.call_args[0]
        
        # Verify sudo -S script execution
        self.assertIn('sudo -S bash /tmp/_warn_cleanup.sh', called_command)
        
        encoded_part = called_command.split('|')[0].strip().split(' ')[1]
        decoded_script = base64.b64decode(encoded_part).decode()
        
        # Verify launchctl asuser usage
        self.assertIn('launchctl asuser "$USER_ID"', decoded_script)
        self.assertIn('display alert "Maintenance Requise"', decoded_script)
        
        print("Verification of updated command logic successful!")

if __name__ == '__main__':
    unittest.main()
