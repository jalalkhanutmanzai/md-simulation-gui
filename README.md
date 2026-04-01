# md-simulation-gui

Desktop GUI for running remote molecular simulation workflows over SSH.

## GROMACS protocol integration

The **GROMACS** engine in the app can now run the
[`jalalkhanutmanzai/gromacs-md-protocol`](https://github.com/jalalkhanutmanzai/gromacs-md-protocol)
workflow directly on your remote server.

### Basic usage

1. In **Connection Setup**, configure SSH access and your remote workdir (default: `~/md_jobs`).
2. In **File Upload**, upload relevant protocol inputs as needed:
   - `protein_clean.pdb`
   - `lig_ini.pdb`
   - `*.itp` (copied as `lig.itp`)
   - `*.prm` (copied as `lig.prm`)
   - `config.env` (optional; copied to `config/config.env`)
3. In **Configuration**:
   - Keep engine as **GROMACS**
   - Optionally adjust protocol repo URL, branch (default `master`), and run command.
4. Click **Run Simulation**.

During execution, the GUI clones/updates the protocol repository in the remote workdir,
places uploaded inputs into the expected protocol folders, and runs the configured workflow
command (default: `bash scripts/run_complete_workflow.sh`).

> Note: the GUI exports `MD_SIM_LENGTH_NS` on the remote shell before running the
> protocol command. If your protocol scripts support it, you can consume this value.
