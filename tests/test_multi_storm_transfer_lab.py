import unittest

import torch

from multi_storm_transfer_lab import forcing_memory


class MultiStormTransferLabTests(unittest.TestCase):
    def test_forcing_memory_preserves_constant_input(self):
        forcing = torch.full((20,), 2.5, dtype=torch.float64)
        memory = forcing_memory(forcing, torch.ones(20, dtype=torch.bool), 6.0)
        self.assertTrue(torch.allclose(memory, forcing))

    def test_forcing_memory_resets_after_invalid_gap(self):
        forcing = torch.tensor([4.0, 0.0, 999.0, 2.0], dtype=torch.float64)
        valid = torch.tensor([True, True, False, True])
        memory = forcing_memory(forcing, valid, 3.0)
        self.assertEqual(memory[2].item(), 0.0)
        self.assertEqual(memory[3].item(), 2.0)


if __name__ == "__main__":
    unittest.main()
