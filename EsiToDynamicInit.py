import xml.etree.ElementTree as ET
import math
import sys


def parse_ethercat_int(val_str):
    if not val_str:
        return 0
    val_str = val_str.strip()
    if val_str.startswith("#x") or val_str.startswith("0x") or val_str.startswith("0X"):
        return int(val_str[2:], 16)
    return int(val_str)


def parse_ethercat_bool(val_str, default=False):
    if val_str is None:
        return default
    return val_str.strip().lower() in ("1", "true")


def parse_hex_bytes(hex_str):
    if not hex_str:
        return b""
    cleaned = "".join(hex_str.split())
    return bytes.fromhex(cleaned)


def get_all_pdos(device_elem):
    pdos = []
    for direction in ("RxPdo", "TxPdo"):
        for pdo in device_elem.findall(direction):
            idx_elem = pdo.find("Index")
            name_elem = pdo.find("Name")
            if idx_elem is None or not idx_elem.text:
                continue

            pdo_index = parse_ethercat_int(idx_elem.text)
            pdo_name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
            sm_attr = pdo.get("Sm")
            default_sm = int(sm_attr) if sm_attr is not None else None

            total_bits = 0
            for entry in pdo.findall("Entry"):
                bit_len = entry.find("BitLen")
                if bit_len is not None and bit_len.text:
                    total_bits += parse_ethercat_int(bit_len.text)

            pdos.append({
                "direction": direction,
                "index": pdo_index,
                "name": pdo_name,
                "default_sm": default_sm,
                "bits": total_bits,
                "bytes": math.ceil(total_bits / 8),
            })
    return pdos


def get_dc_modes(device_elem):
    modes = []
    for op in device_elem.findall("./Dc/OpMode"):
        name_elem = op.find("Name")
        desc_elem = op.find("Desc")
        assign_elem = op.find("AssignActivate")
        c0_elem = op.find("CycleTimeSync0")
        s0_elem = op.find("ShiftTimeSync0")
        c1_elem = op.find("CycleTimeSync1")
        s1_elem = op.find("ShiftTimeSync1")

        name = name_elem.text.strip() if name_elem is not None and name_elem.text else "Unnamed"
        desc = desc_elem.text.strip() if desc_elem is not None and desc_elem.text else ""
        assign_val = parse_ethercat_int(assign_elem.text) if assign_elem is not None and assign_elem.text else 0

        c0_ns = parse_ethercat_int(c0_elem.text) if c0_elem is not None and c0_elem.text else 0
        c0_factor = int(c0_elem.get("Factor")) if (c0_elem is not None and c0_elem.get("Factor")) else 1
        s0_ns = parse_ethercat_int(s0_elem.text) if s0_elem is not None and s0_elem.text else 0

        c1_ns = parse_ethercat_int(c1_elem.text) if c1_elem is not None and c1_elem.text else 0
        c1_factor = int(c1_elem.get("Factor")) if (c1_elem is not None and c1_elem.get("Factor")) else 1
        s1_ns = parse_ethercat_int(s1_elem.text) if s1_elem is not None and s1_elem.text else 0

        modes.append({
            "name": name,
            "desc": desc,
            "assign_activate": assign_val,
            "c0_ns": c0_ns,
            "c0_factor": c0_factor,
            "s0_ns": s0_ns,
            "c1_ns": c1_ns,
            "c1_factor": c1_factor,
            "s1_ns": s1_ns,
        })
    return modes


def get_coe_init_cmds(device_elem):
    init_cmds = []
    for cmd in device_elem.findall("./Mailbox/CoE/InitCmd"):
        idx_elem = cmd.find("Index")
        sub_elem = cmd.find("SubIndex")
        data_elem = cmd.find("Data")
        comment_elem = cmd.find("Comment")
        timeout_elem = cmd.find("Timeout")

        if idx_elem is None or not idx_elem.text:
            continue

        index = parse_ethercat_int(idx_elem.text)
        subindex = parse_ethercat_int(sub_elem.text) if sub_elem is not None and sub_elem.text else 0
        raw_bytes = parse_hex_bytes(data_elem.text) if data_elem is not None and data_elem.text else b""
        comment = comment_elem.text.strip() if comment_elem is not None and comment_elem.text else ""
        timeout = parse_ethercat_int(timeout_elem.text) if timeout_elem is not None and timeout_elem.text else 1000
        complete_access = parse_ethercat_bool(cmd.get("CompleteAccess"), default=False)
        transitions = [t.text.strip() for t in cmd.findall("Transition") if t.text]

        init_cmds.append({
            "index": index,
            "subindex": subindex,
            "bytes": raw_bytes,
            "length": len(raw_bytes),
            "comment": comment,
            "timeout": timeout,
            "complete_access": complete_access,
            "transitions": transitions,
        })
    return init_cmds


def generate_st_from_esi(
    esi_path,
    selected_pdo_indices=None,
    selected_dc_name=None,
    master_cycle_us=1000,
    slave="fbSlave",
):
    tree = ET.parse(esi_path)
    root = tree.getroot()

    sm_type_map = {
        "Inputs": (0, "ETHERCAT_INPUTs"),
        "Outputs": (1, "ETHERCAT_OUTPUTS"),
        "MBoxIn": (2, "ETHERCAT_MAILBOXIN"),
        "MBoxOut": (3, "ETHERCAT_MAILBOXOUT"),
    }

    for dev_idx, device in enumerate(root.findall(".//Descriptions/Devices/Device")):
        type_elem = device.find("Type")
        dev_name = type_elem.text.strip() if type_elem is not None and type_elem.text else f"Device_{dev_idx}"
        all_pdos = get_all_pdos(device)
        dc_modes = get_dc_modes(device)
        init_cmds = get_coe_init_cmds(device)

        # Select DC OpMode
        active_dc = None
        if dc_modes:
            if selected_dc_name:
                active_dc = next((m for m in dc_modes if m["name"].lower() == selected_dc_name.lower()), None)
            else:
                active_dc = next((m for m in dc_modes if m["assign_activate"] != 0), dc_modes[0])

        # Select active PDOs: override if user passed indices, otherwise use default Sm assignments
        if selected_pdo_indices is not None:
            requested_set = set(selected_pdo_indices)
            active_pdos = [p for p in all_pdos if p["index"] in requested_set]
            found_set = {p["index"] for p in active_pdos}
            missing = requested_set - found_set
            if missing:
                missing_str = ", ".join(f"16#{m:04X}" for m in sorted(missing))
                print(f"// WARNING: Requested PDO(s) not found in {dev_name}: {missing_str}")
        else:
            active_pdos = [p for p in all_pdos if p["default_sm"] is not None]

        active_rx = [p for p in active_pdos if p["direction"] == "RxPdo"]
        active_tx = [p for p in active_pdos if p["direction"] == "TxPdo"]

        skip_assign_indices = {0x1C12, 0x1C13} if selected_pdo_indices is not None else set()
        filtered_init_cmds = [c for c in init_cmds if c["index"] not in skip_assign_indices]

        large_buffers = []
        for i, cmd in enumerate(filtered_init_cmds):
            if cmd["length"] > 4:
                var_name = f"abyInitCmd_{dev_idx}_{i}_{cmd['index']:04X}"
                byte_literals = ", ".join(f"16#{b:02X}" for b in cmd["bytes"])
                large_buffers.append((var_name, cmd["length"], byte_literals, cmd["comment"]))

        print("// ============================================================================")
        print(f"// Device: {dev_name}")
        if dc_modes:
            print("// Available DC OpModes in ESI:")
            for m in dc_modes:
                print(f"//   '{m['name']}' (AssignActivate: 16#{m['assign_activate']:04X}) - {m['desc']}")
        print("// Available PDOs in ESI:")
        for p in all_pdos:
            is_selected = " <-- SELECTED" if p in active_pdos else ""
            flag = f"Default SM{p['default_sm']}" if p["default_sm"] is not None else "Optional"
            print(f"//   [{p['direction']}] 16#{p['index']:04X} ({p['bytes']} bytes) - {p['name']} [{flag}]{is_selected}")
        print("// ============================================================================")

        if large_buffers:
            print("VAR")
            for var_name, length, byte_literals, comment in large_buffers:
                cmt = f" // {comment}" if comment else ""
                print(f"    {var_name} : ARRAY [0..{length - 1}] OF BYTE := [{byte_literals}];{cmt}")
            print("END_VAR\n")

        # 1. Distributed Clocks
        if active_dc is not None:
            print(f"// --- 1. Distributed Clocks ({active_dc['name']}) ---")
            assign = active_dc["assign_activate"]
            x_enable_dc = bool(assign & 0x0100) or (assign != 0)
            x_enable_sync0 = bool(assign & 0x0200)
            x_enable_sync1 = bool(assign & 0x0400)
            low_byte = assign & 0xFF

            if x_enable_sync0:
                c0_us = (active_dc["c0_ns"] // 1000) if active_dc["c0_ns"] > 0 else (master_cycle_us * active_dc["c0_factor"])
            else:
                c0_us = 0
            s0_us = active_dc["s0_ns"] // 1000

            if x_enable_sync1:
                c1_us = (active_dc["c1_ns"] // 1000) if active_dc["c1_ns"] > 0 else (master_cycle_us * active_dc["c1_factor"])
            else:
                c1_us = 0
            s1_us = active_dc["s1_ns"] // 1000

            print(
                f"{slave}.SetDCSettings("
                f"{str(x_enable_dc).upper()}, {str(x_enable_sync0).upper()}, "
                f"{c0_us}, {s0_us}, "
                f"{str(x_enable_sync1).upper()}, {c1_us}, {s1_us}, "
                f"16#{low_byte:02X}); // {active_dc['name']} (AssignActivate: 16#{assign:04X})\n"
            )

        # 2. ESI CoE InitCmds
        print("// --- 2. ESI CoE InitCmds ---")
        buf_counter = 0
        for cmd in filtered_init_cmds:
            ca_str = "TRUE" if cmd["complete_access"] else "FALSE"
            trans_str = f" [{'/'.join(cmd['transitions'])}]" if cmd["transitions"] else ""
            cmt_str = f" // {cmd['comment']}{trans_str}" if (cmd["comment"] or trans_str) else ""

            if cmd["length"] <= 4:
                val = int.from_bytes(cmd["bytes"], byteorder="little", signed=False)
                print(
                    f"{slave}.AddCoEInit("
                    f"16#{cmd['index']:04X}, {cmd['subindex']}, {cmd['length']}, "
                    f"16#{val:X}, {cmd['timeout']}, {ca_str}, FALSE);{cmt_str}"
                )
            else:
                var_name = large_buffers[buf_counter]
                buf_counter += 1
                print(
                    f"{slave}.AddCoEInit("
                    f"16#{cmd['index']:04X}, {cmd['subindex']}, {cmd['length']}, "
                    f"ADR({var_name}), {cmd['timeout']}, {ca_str}, TRUE);{cmt_str}"
                )

        # 3. Custom PDO Assignment Commands
        cmt = chr(47) * 2
        if selected_pdo_indices is not None:
            print(f"\n{cmt} --- 3. Custom PDO Assignment (Overrides ESI 16#1C12 / 16#1C13) ---")
            for assign_idx, pdo_group, label in [
                (0x1C12, active_rx, "SM2 RxPDO Assign"),
                (0x1C13, active_tx, "SM3 TxPDO Assign"),
            ]:
                if pdo_group:
                    pdo_list_str = ", ".join(f"16#{p['index']:04X}" for p in pdo_group)
                    print(f"{cmt} {label}: [{pdo_list_str}]")
                    print(f"{slave}.AddCoEInit(16#{assign_idx:04X}, 0, 1, 0, 1000, FALSE, FALSE);")
                    for sub_idx, p in enumerate(pdo_group, start=1):
                        print(f"{slave}.AddCoEInit(16#{assign_idx:04X}, {sub_idx}, 2, 16#{p['index']:04X}, 1000, FALSE, FALSE);")
                    print(f"{slave}.AddCoEInit(16#{assign_idx:04X}, 0, 1, {len(pdo_group)}, 1000, FALSE, FALSE);")

        # 4. SyncManagers
        print(f"\n{cmt} --- 4. SyncManagers ---")
        sm_list = []
        for idx, sm in enumerate(device.findall("Sm")):
            sm_role = sm.text.strip() if sm.text else ""
            start_addr = parse_ethercat_int(sm.get("StartAddress"))
            default_size = parse_ethercat_int(sm.get("DefaultSize"))
            control_byte = parse_ethercat_int(sm.get("ControlByte"))
            usi_type, type_comment = sm_type_map.get(sm_role, (0, f"UNKNOWN({sm_role})"))

            if sm_role == "Outputs":
                length = sum(p["bytes"] for p in active_rx)
                x_enable = length > 0
            elif sm_role == "Inputs":
                length = sum(p["bytes"] for p in active_tx)
                x_enable = length > 0
            else:
                length = default_size
                x_enable = parse_ethercat_bool(sm.get("Enable"), default=True)

            sm_info = {
                "index": idx,
                "role": sm_role,
                "start_addr": start_addr,
                "length": length,
                "control_byte": control_byte,
                "x_enable": x_enable,
                "usi_type": usi_type,
            }
            sm_list.append(sm_info)

            st_bool = "TRUE" if x_enable else "FALSE"
            print(
                f"{slave}.AddSyncManager("
                f"16#{start_addr:04X}, {length}, 16#{control_byte:02X}, {st_bool}, {usi_type}); "
                f"{cmt} SM{idx}: {type_comment}"
            )

        # 5. FMMUs + AlignFMMU
        print(f"\n{cmt} --- 5. FMMUs ---")
        for fmmu_idx, fmmu in enumerate(device.findall("Fmmu")):
            fmmu_role = fmmu.text.strip() if fmmu.text else ""
            sm_attr = fmmu.get("Sm")

            if fmmu_role == "MBoxState":
                print(f"{slave}.AddFMMU(0, 1, 0, 0, 16#080D, 0, 1, 1); {cmt} FMMU{fmmu_idx}: MBoxState")
                continue

            target_sm = (
                next((s for s in sm_list if s["index"] == int(sm_attr)), None)
                if sm_attr is not None
                else next((s for s in sm_list if s["role"] == fmmu_role), None)
            )

            if target_sm and target_sm["length"] > 0:
                usi_access = 1 if fmmu_role == "Inputs" else 2
                print(
                    f"{slave}.AddFMMU("
                    f"0, {target_sm['length']}, 0, 7, 16#{target_sm['start_addr']:04X}, 0, {usi_access}, 1); "
                    f"{cmt} FMMU{fmmu_idx}: {fmmu_role} -> SM{target_sm['index']}"
                )

        print(f"{slave}.AlignFMMU();\n\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python esi_to_st.py <esi_file.xml> [0x1601 0x1A02 ...] [--dc \"DC Sync0\"] [--cycle 1000]")
    else:
        esi_file = sys.argv[1]
        custom_pdos = []
        dc_name = None
        cycle_us = 1000

        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i] == "--dc" and i + 1 < len(args):
                dc_name = args[i + 1]
                i += 2
            elif args[i] == "--cycle" and i + 1 < len(args):
                cycle_us = int(args[i + 1])
                i += 2
            else:
                custom_pdos.append(parse_ethercat_int(args[i]))
                i += 1

        generate_st_from_esi(
            esi_file,
            selected_pdo_indices=custom_pdos if custom_pdos else None,
            selected_dc_name=dc_name,
            master_cycle_us=cycle_us,
        )
        