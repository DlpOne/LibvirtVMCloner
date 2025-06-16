#!/usr/bin/python

import libvirt
import time
import argparse
import os
from lxml import etree
from subprocess import run
import code



def parse_args():
    parser = argparse.ArgumentParser(
        description="Clone VM with different options"
    )
    
    parser.add_argument("-l", "--linked", action="store_true", help="Create linked clone")
    parser.add_argument("-s", "--snapshot", metavar="SNAP_NAME", help="Use specified snapshot")
    parser.add_argument("-c", "--create", action="store_true", help="Create snapshot before cloning")
    parser.add_argument("vm_name", metavar="VM_NAME", help="Original VM name")
    parser.add_argument("vm_clone", metavar="VM_CLONE", help="Clone VM name")

    args = parser.parse_args()

    if not args.vm_name or not args.vm_clone:
        parser.print_usage()
        exit(1)

    if(args.create and not args.snapshot):
        print ("Error create can't be set without -s snapname")
        exit(1)

    return args

def vmactive(vm):
    if vm.isActive():
        return False

    return True

def waitfor(timeout,interval,func,*args,**kwargs):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if func(*args,**kwargs):
           return True
        time.sleep(interval)

    return False

def PoolGetFilepath(conn,pool,volume):
    pool=conn.storagePoolLookupByName(pool)
    
    if not pool:
        return None
    
    poolxml=etree.fromstring(pool.XMLDesc())
    
    if poolxml == None :
        return None
    
    type=poolxml.get("type")

    if type != "dir":
        return None
        
    paths=poolxml.xpath("//target/path/text()")

    if not paths:
        return None
    
    path=paths[0]

    return f"{path}/{volume}"

def ValidateDisks(vmxml):
    disksxml = vmxml.xpath("//domain/devices/disk")

    for disk in disksxml:
        disktype=disk.get("type")
        diskdevice=disk.get("device")
        driver = disk.find("driver")

        if diskdevice == "cdrom":
            continue

        if diskdevice != "disk":
            print("Error unsupported Disk Device Type found")
            return
        

        if driver!=None and driver.get("type") != "qcow2":
            print ("Disks without qcow2 format are not supported")
            return False
        
        if disktype not in ["file","volume"]:
            print ("Unsuuported Disk Type")
            return False
    
    return True


def internalSnap(conn,vmxml,snap=False):
    internal = False

    if snap:
        disksxml = vmxml.xpath("//disks/disk")

        for disk in disksxml:
            snaptype = disk.get("snapshot")

            if snaptype and snaptype == "internal":
                return True
            
        return False
    

    disksxml = vmxml.xpath("//domain/devices/disk")
    for disk in disksxml:
        filepath=""
        disktype=disk.get("type")
        diskdevice=disk.get("device")
        source = disk.find("source")


        if diskdevice != "disk":
            continue

        if disktype == 'file':
            filepath=source.get("file")
        elif disktype == "volume":
            pool=source.get("pool")
            volume=source.get("volume")

            filepath=PoolGetFilepath(conn,pool,volume)
        else:
            continue

        
        internal=run(f'qemu-img snapshot -l {filepath} | wc -l',capture_output=True,shell=True)

        if int(internal.stdout) > 0:
            return True
        
    return False

def main(args):
    snap=None
    vm=None
    vmxml=None
    snapinternal=None

    conn=libvirt.open("qemu:///system")

    try:
        vm = conn.lookupByName( args.vm_name )
    except:
        print (f"Error VM {args.vm_name} not found")
        return 1
    
    try:
        vm_clone = conn.lookupByName( args.vm_clone )

        if vm_clone:
            print (f"Error Clone Name {args.vm_clone} already exists")
            return 1
        
    except:
        pass

    
    if args.snapshot and not args.create:
        try:
            snap = vm.snapshotLookupByName(args.snapshot)
        except:
            print (f"Error snapshot {args.snapshot} not found")
            return 1


    if snap:
        vmxml=etree.fromstring(snap.getXMLDesc())
    else:
        vmxml=etree.fromstring(vm.XMLDesc())

    print ("validate Disks: ")
    
    if not ValidateDisks(vmxml):
        print ("Not Supported disks found")
        return 1

    print("All Disks Supported")

    snapinternal=internalSnap(conn,vmxml,(snap != None))    
    print (f"Snapshot internal: {snapinternal}")

    if(args.create and snapinternal):
        print ("Error can't create an external snapshot on VM with internal Snapshots")
        return 1
    
    if (args.linked and snapinternal and snap):
        print ("Error can't create linked Clone on internal Snapshot")
        return 1
    

    if not snap and vm.isActive():
        print (f"VM {args.vm_name} running ... shutdown")
        vm.shutdown()
        if not waitfor(60,1,vmactive,vm):
            print(f"Error can't sutdown VM {args.vm_name} stopping VM")
            vm.destroy() 

    if snap:
        vmxml=etree.fromstring(snap.getXMLDesc())
        vmxml=vmxml.find("domain")
        vmxml=etree.fromstring(etree.tounicode(vmxml))
    else:
        vmxml=etree.fromstring(vm.XMLDesc())


    if vmxml==None:
        print ("Error cant get xml infos of VM")
        return 1
    
    namenode=vmxml.xpath("/domain/name")    
    namenode[0].text=args.vm_clone

    uuidnode=vmxml.find("uuid")
    vmxml.remove(uuidnode)
    
    macnodes = vmxml.xpath('/domain/devices/interface/mac')
    if macnodes != None:
        for macnode in macnodes:
            parent = macnode.getparent()
            parent.remove(macnode)


    disknodes = vmxml.xpath('/domain/devices/disk')

    if not disknodes:
        print ("Error no disks found")
        return 1
    
    disks=list()
    
    for disknode in disknodes:
        dsksrcpath=None
        device = disknode.get("device")

        if device not in ["disk", "cdrom"]:
            print ("Unsupported Disk found ")
            return 1
        
        if device == "cdrom":
            continue

        type = disknode.get("type")
        sourcenode=disknode.xpath("./source")[0]

        if type == "volume":
            pool=sourcenode.get("pool")
            volume=sourcenode.get("volume")
            print(f"pool: {pool} volume: {volume}")
            dsksrcpath=PoolGetFilepath(conn,pool,volume)
        elif type == "file":
            dsksrcpath=sourcenode.get("file")
        else:
            print (f"Error Disk type{type} not supported")
            return 1
            
        dstpath=os.path.dirname(dsksrcpath)
        dstfile=os.path.basename(dsksrcpath)
        dskdstpath=f"{dstpath}/{args.vm_clone}_{dstfile}"

        disknode.set("type","file")
        sourcenode.attrib.clear()             
        sourcenode.set('file', dskdstpath) 

        disks.append([dsksrcpath,dskdstpath])

        backingnodes=disknode.xpath("./backingStore")
        backingnode=backingnode[0] if (len(backingnodes)!=0) else None
        if backingnode != None:
            disknode.remove(backingnode)

        if args.linked:
            backingroot = etree.Element("backingStore")
            backingroot.set("type","file")

            backingsource = etree.SubElement(backingroot, "source")
            backingsource.set("file",dsksrcpath)

            backingformat=etree.SubElement(backingroot, "format")
            backingformat.set("type",'qcow2')

            if(backingnode != None):
                backingroot.append(backingnode)
            
            disknode.append(backingroot)
            
    print ("Clone Disks: ")


    for (srcpath,dstpath) in disks:
        success=None
        
        print (f"Clone Disk from {srcpath} to {dstpath}: ..... ", end="")

        if args.linked:
            sucess=run(f'qemu-img create -f qcow2 -o backing_fmt=qcow2 -b {srcpath} {dstpath}',shell=True)
        elif snapinternal and args.snapshot:
            sucess=run(f'qemu-img convert -p -O qcow2 -l {args.snapshot} {srcpath} {dstpath}',shell=True)
        else:
            sucess=run(f'qemu-img convert -O qcow2 -p {srcpath} {dstpath}',shell=True)
            
            
        if sucess.returncode != 0:
            print (f"Error cloning disk")
            return 1
        
        print("done")

    print(etree.tostring(vmxml,encoding="unicode"))
    clonedom = conn.defineXML(etree.tostring(vmxml,encoding="unicode"))
    if clonedom == None:
        print (f"Error can't create Clone:\n {etree.tostring(vmxml,encoding="unicode")}")
        return 1

    print(f"Clone erfolgreich erstellt.")

    return 0

if __name__ == "__main__":
    args = parse_args()
    main(args)
