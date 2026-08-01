SHELL         := /bin/bash
.SHELLFLAGS   := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV                 ?= uv
INSTALL            ?= install
FONTDIR            ?= $(HOME)/Library/Fonts
PYTHON             := $(UV) run python
RUFF               := $(UV) run ruff
FONTS              := SummerGhost-Regular.ttf SummerGhost-Bold.ttf SummerGhost-Italic.ttf SummerGhost-BoldItalic.ttf
HELP_NAME_WIDTH    := 18
HELP_EXAMPLE_WIDTH := 42

##@ Development

.PHONY: build
build: ## Build all font styles into dist/
	@$(PYTHON) scripts/build.py

.PHONY: fmt
fmt: ## Format Python sources. Use CHECK_ONLY=1 to check only
	@if [ "$(CHECK_ONLY)" = "1" ]; then \
		$(RUFF) format --check scripts; \
	else \
		$(RUFF) format scripts; \
	fi

.PHONY: lint
lint: ## Run static Python checks
	@$(RUFF) check scripts
	@$(UV) run mypy scripts

.PHONY: validate
validate: build ## Validate names, metrics, coverage, and shaping
	@$(PYTHON) scripts/validate.py

.PHONY: specimen
specimen: build ## Render dist/specimen.png for visual inspection
	@$(PYTHON) scripts/render_specimen.py

.PHONY: check
check: ## Run formatting, lint, build, and validation checks
	@$(MAKE) --no-print-directory fmt CHECK_ONLY=1
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory validate

.PHONY: clean
clean: ## Remove downloads and generated artifacts
	@$(PYTHON) scripts/build.py --clean

##@ Installation

.PHONY: install
install: validate ## Install all styles into FONTDIR
	@mkdir -p "$(FONTDIR)"
	@for font in $(FONTS); do $(INSTALL) -m 0644 "dist/$$font" "$(FONTDIR)/$$font"; done
	@printf 'Installed Summer Ghost into %s\n' "$(FONTDIR)"

.PHONY: uninstall
uninstall: ## Remove Summer Ghost from FONTDIR
	@for font in $(FONTS); do rm -f "$(FONTDIR)/$$font"; done
	@printf 'Removed Summer Ghost from %s\n' "$(FONTDIR)"

##@ Help

.PHONY: help
help: ## Show this help message
	@awk -v width="$(HELP_NAME_WIDTH)" 'BEGIN {FS = ":.*##"} \
		{ lines[NR] = $$0 } \
		END { \
			section = ""; \
			for (i = 1; i <= NR; i++) { \
				$$0 = lines[i]; \
				if ($$0 ~ /^##@/) section = substr($$0, 5); \
				else if ($$0 ~ /^[a-zA-Z0-9_.-]+:.*##/) { \
					split($$0, parts, ":.*##"); \
					sub(/^[[:space:]]+/, "", parts[2]); \
					if (section != "") printf "\n\033[1m%s\033[0m\n", section; \
					section = ""; \
					printf "  \033[36m%-*s\033[0m%s\n", width, parts[1], parts[2]; \
				} \
			} \
		}' $(MAKEFILE_LIST)
	@printf '\n\033[1mVariables:\033[0m\n'
	@printf '  \033[36m%-*s\033[0m%s\n' "$(HELP_NAME_WIDTH)" "FONTDIR" "Install directory, defaults to $(FONTDIR)"
	@printf '\n\033[1mExamples:\033[0m\n'
	@printf '  \033[36m%-*s\033[0m%s\n' "$(HELP_EXAMPLE_WIDTH)" "make check" "# Run all quality gates"
	@printf '  \033[36m%-*s\033[0m%s\n' "$(HELP_EXAMPLE_WIDTH)" "make install" "# Build, validate, and install"
	@printf '  \033[36m%-*s\033[0m%s\n' "$(HELP_EXAMPLE_WIDTH)" "make install FONTDIR=/path/to/fonts" "# Override the install directory"
