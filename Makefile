# Regenerate the generated consensus-specs fork types (consensus-spec/eth_consensus_specs).
#
# Pin the source commit here; keep it in sync with consensus-spec/PROVENANCE.md.
# Requires `uv` (https://github.com/astral-sh/uv). The generated code is types only and must
# never be hand-edited — change the spec commit and rerun this target instead.

CSPECS_REPO ?= https://github.com/ethereum/consensus-specs.git
CSPECS_COMMIT ?= 09c77a4a74c2a21bea143486f06163581b4f5563
CSPECS_DIR ?= /tmp/cspecs
VENDOR_DIR := consensus-spec/eth_consensus_specs
FORKS := phase0 altair bellatrix capella deneb electra fulu gloas

.PHONY: regen-specs
regen-specs:
	rm -rf $(CSPECS_DIR)
	git clone $(CSPECS_REPO) $(CSPECS_DIR)
	cd $(CSPECS_DIR) && git checkout $(CSPECS_COMMIT)
	cd $(CSPECS_DIR) && uv run --python 3.14 python -m pysetup.generate_specs --all-forks
	@src="$(CSPECS_DIR)/tests/core/pyspec/eth_consensus_specs"; dst="$(VENDOR_DIR)"; \
	rm -rf "$$dst"; mkdir -p "$$dst"; \
	cp "$$src/__init__.py" "$$src/py.typed" "$$dst/"; \
	for f in $(FORKS); do mkdir -p "$$dst/$$f"; cp "$$src/$$f/mainnet.py" "$$src/$$f/__init__.py" "$$dst/$$f/"; done; \
	mkdir -p "$$dst/utils/ssz"; \
	cp "$$src/utils/__init__.py" "$$src/utils/bls.py" "$$src/utils/kzg.py" "$$src/utils/merkle_minimal.py" "$$dst/utils/"; \
	cp "$$src/utils/ssz/__init__.py" "$$src/utils/ssz/bytes.py" "$$src/utils/ssz/ssz_impl.py" "$$dst/utils/ssz/"; \
	mkdir -p "$$dst/test/helpers"; \
	cp "$$src/test/__init__.py" "$$dst/test/__init__.py"; \
	cp "$$src/test/helpers/__init__.py" "$$dst/test/helpers/__init__.py"; \
	cp "$$src/test/helpers/merkle.py" "$$dst/test/helpers/merkle.py"
	@echo "Regenerated $(VENDOR_DIR) from $(CSPECS_COMMIT)."
	@echo "PROVENANCE.md lives in consensus-spec/ (outside the regenerated dir) — update its commit/date if it changed."
