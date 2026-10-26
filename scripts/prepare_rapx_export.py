"""Attach a serialization-only hook to a pinned external RAPx checkout."""
import argparse
from pathlib import Path
import shutil


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkout',type=Path,required=True)
    args=p.parse_args();folder=args.checkout/'rapx/src/analysis/dataflow'
    destination=folder/'project_map_export.rs'
    if destination.exists():raise ValueError('Choose an unmodified upstream export checkout')
    shutil.copyfile(Path(__file__).resolve().parents[1]/'adapters/rapx_export.rs',destination)
    module=folder/'mod.rs';module.write_text(module.read_text()+'\npub mod project_map_export;\n')
    driver=folder/'default.rs';text=driver.read_text();needle='        self.build_graphs();\n'
    if text.count(needle)!=1:raise ValueError('Pinned upstream exporter hook changed')
    driver.write_text(text.replace(needle,needle+'        super::project_map_export::write(self);\n'))
    print('Installed serialization-only RAPx hook; upstream analysis implementations unchanged')


if __name__=='__main__':main()
