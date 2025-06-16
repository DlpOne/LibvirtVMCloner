# LibvirtVMCloner

This script allows the creation of different types of Libvirt VM clones.  
The source of the clone can be either the current state of the VM or a specific existing internal or external snapshot. If needed, a new snapshot can also be created.  
The script supports creating both full clones and *linked* (copy-on-write) clones. However, linked clones can only be created from the current state of the VM or from an external snapshot.

---

## Usage

```bash
Usage: vmcloner.py [options] VM_NAME VM_CLONE
```

### Positional arguments:
- `VM_NAME` – Original VM name  
- `VM_CLONE` – Name for the new cloned VM

### Optional arguments:
- `-l`, `--linked` – Create a linked (copy-on-write) clone  
- `-s SNAP_NAME`, `--snapshot SNAP_NAME` – Use specified snapshot as the source  
- `-c`, `--create` – Create a snapshot before cloning

---

## Examples

```bash
script.py myvm myvm-clone
# Create a full clone of 'myvm' named 'myvm-clone'

script.py -s snap1 myvm myvm-clone
# Create a full clone of snapshot 'snap1' from 'myvm' to 'myvm-clone'

script.py -l myvm myvm-clone
# Create a linked (copy-on-write) clone of 'myvm' to 'myvm-clone'

script.py -s snap1 -l myvm myvm-clone
# Create a linked (copy-on-write) clone of external snapshot 'snap1' from 'myvm' to 'myvm-clone'

script.py -c -s snap1 -l myvm myvm-clone
# Create a linked (copy-on-write) clone using a newly created external snapshot 'snap1' of 'myvm'
```

---

## ⚠️ Attention

If you create a **linked clone from the current state**, **do not power on or modify the source VM** afterward — doing so may corrupt the clone.
Similarly, if you create a **linked clone from a snapshot**, that snapshot **must not be deleted or modified** afterward.  
Otherwise, the clone’s virtual disk will become **corrupted** due to the loss of its backing data.
