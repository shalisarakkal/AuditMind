"""Curated compliance standards knowledge base (CIS Controls v8, NIST CSF 2.0, ISO/IEC 27001:2022).
Used to populate RAG embeddings for AI-powered resilience auditing and citations.
"""

STANDARDS_DATA = [
    # ==========================================
    # CIS Controls v8
    # ==========================================
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-1.1",
        "title": "Establish and Maintain a Detailed Enterprise Asset Inventory",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 1: Inventory and Control of Enterprise Assets",
        "content": (
            "Establish and maintain an accurate, detailed, and up-to-date inventory of all enterprise assets "
            "with the potential to store or process data. Include IP address, MAC address, device name, "
            "owner, and whether the asset is authorized. Scan network ranges periodically to identify unmanaged devices."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-2.1",
        "title": "Establish and Maintain a Software Inventory",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 2: Inventory and Control of Software Assets",
        "content": (
            "Establish and maintain a detailed inventory of all licensed software and operating systems "
            "installed across enterprise assets. Track version, patch level, and business purpose. "
            "Ensure unauthorized software is identified, isolated, and removed."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-4.1",
        "title": "Establish and Maintain a Secure Configuration Process",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 4: Secure Configuration of Enterprise Assets and Software",
        "content": (
            "Maintain documented baseline security configurations for operating systems, cloud services, "
            "and network devices. Disable unnecessary ports, protocols, and default accounts. "
            "Audit configurations continuously against CIS Benchmarks."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-5.1",
        "title": "Establish and Maintain an Inventory of Accounts",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 5: Account Management",
        "content": (
            "Maintain an active inventory of all user and service accounts, including administrator accounts. "
            "Revoke inactive accounts after 90 days of non-use. Enforce centralized identity management and strong authentication."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-5.2",
        "title": "Use Unique Passwords and Multi-Factor Authentication",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 5: Account Management",
        "content": (
            "Enforce unique, complex passwords and multi-factor authentication (MFA) across all administrative accounts, "
            "remote access VPNs, cloud management consoles, and sensitive enterprise applications."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-6.1",
        "title": "Establish an Access Granting Process",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 6: Access Control Management",
        "content": (
            "Implement role-based access control (RBAC) following the principle of least privilege. "
            "Regularly review privileged memberships and immediately revoke permissions upon role change or employee termination."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-7.1",
        "title": "Establish and Maintain a Vulnerability Management Process",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 7: Continuous Vulnerability Management",
        "content": (
            "Perform regular automated vulnerability scans across all internal, external, and cloud infrastructure. "
            "Prioritize remediation based on exploit availability (EPSS / CISA KEV), CVSS severity, and asset criticality."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-8.1",
        "title": "Establish and Maintain an Audit Log Management Process",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 8: Audit Log Management",
        "content": (
            "Enable comprehensive audit logging across identity systems, network boundaries, cloud management planes, "
            "and endpoints. Collect logs centrally with synchronized time (NTP), encrypt in transit and at rest, and retain for at least 365 days."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-10.1",
        "title": "Deploy and Maintain Anti-Malware Software",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 10: Malware Defenses",
        "content": (
            "Deploy centralized endpoint detection and response (EDR) or anti-malware tools across all servers, workstations, "
            "and cloud instances. Ensure real-time protection, signature auto-updates, and behavioral monitoring are active."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-11.1",
        "title": "Establish and Maintain a Data Recovery Process",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 11: Data Recovery",
        "content": (
            "Perform regular automated backups of critical data, databases, and system images. Maintain immutable, "
            "isolated (air-gapped) or write-once-read-many (WORM) copies to protect against ransomware. Test restoration quarterly."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-12.1",
        "title": "Ensure Network Infrastructure is Kept Up-to-Date",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 12: Network Infrastructure Management",
        "content": (
            "Segment enterprise networks into distinct security zones (DMZ, management, user, production). "
            "Enforce strict firewall rules, disable legacy unencrypted protocols (Telnet, HTTP, SNMPv1/v2), and inspect ingress/egress traffic."
        ),
    },
    {
        "framework": "CIS",
        "version": "v8",
        "control_id": "CIS-17.1",
        "title": "Designate Personnel to Manage Incident Handling",
        "type": "standard",
        "source": "CIS Controls v8",
        "content_ref": "Control 17: Incident Response Management",
        "content": (
            "Establish a documented incident response plan with clear escalation roles, communication protocols, "
            "containment playbooks, forensic procedures, and post-incident review mechanisms."
        ),
    },

    # ==========================================
    # NIST CSF 2.0
    # ==========================================
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-GV.OC-01",
        "title": "Organizational Context and Cybersecurity Strategy",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Govern (GV) -> Organizational Context",
        "content": (
            "The organization's mission, leadership expectations, legal and regulatory requirements, and risk tolerance "
            "are documented and understood to guide cybersecurity decision-making and resource prioritization."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-ID.AM-01",
        "title": "Inventories of Hardware, Software, and Services",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Identify (ID) -> Asset Management",
        "content": (
            "Inventories of physical and virtual assets, software platforms, cloud services, external dependencies, "
            "and data flows are maintained to identify risk boundaries and asset ownership."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-ID.RA-01",
        "title": "Vulnerabilities in Assets are Identified and Documented",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Identify (ID) -> Risk Assessment",
        "content": (
            "Asset vulnerabilities, misconfigurations, and supply chain dependencies are proactively scanned, analyzed, "
            "and tracked with threat intelligence to determine organizational risk exposure."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-PR.AA-01",
        "title": "Identities and Credentials Management",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Protect (PR) -> Identity Management & Access Control",
        "content": (
            "Identities and credentials for authorized users, services, and hardware are managed through central directories, "
            "strict lifecycle offboarding, multi-factor authentication, and cryptographic session protection."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-PR.AC-01",
        "title": "Least Privilege and Separation of Duties",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Protect (PR) -> Access Control",
        "content": (
            "Access permissions are restricted based on least privilege and separation of duties. "
            "Privileged administrative actions require justification, dual authorization, or just-in-time elevation."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-PR.DS-01",
        "title": "Data Security and Confidentiality",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Protect (PR) -> Data Security",
        "content": (
            "Sensitive data at rest and in transit is protected using approved encryption algorithms (AES-256, TLS 1.3). "
            "Data loss prevention (DLP) and strict access filters prevent unauthorized exfiltration."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-PR.PS-01",
        "title": "Platform Security and Configuration Baselines",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Protect (PR) -> Platform Security",
        "content": (
            "Operating systems, cloud instances, containers, and applications are hardened according to standardized "
            "configuration baselines. Default credentials, unnecessary services, and insecure protocols are removed."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-DE.CM-01",
        "title": "Continuous Network and System Monitoring",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Detect (DE) -> Continuous Monitoring",
        "content": (
            "The enterprise network and environment are monitored continuously to detect anomalous activity, unauthorized "
            "connections, privilege escalation, and lateral movement in real time."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-DE.AE-01",
        "title": "Anomalies and Events are Analyzed",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Detect (DE) -> Adverse Event Analysis",
        "content": (
            "Security events collected by SIEM and EDR platforms are correlated with threat intelligence "
            "to assess attack impact, verify false positives, and trigger automated containment."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-RS.MA-01",
        "title": "Incident Management and Response Execution",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Respond (RS) -> Incident Management",
        "content": (
            "Incident response plans are executed to contain, isolate, and eradicate threats. Forensic evidence "
            "is preserved, and key stakeholders (legal, executive, regulators) are notified according to defined SLAs."
        ),
    },
    {
        "framework": "NIST",
        "version": "2.0",
        "control_id": "NIST-RC.RP-01",
        "title": "Recovery Plan Execution and Business Resilience",
        "type": "standard",
        "source": "NIST CSF 2.0",
        "content_ref": "Recover (RC) -> Incident Recovery",
        "content": (
            "Restoration processes and resilience plans are executed to return critical systems and services to normal "
            "operations while verifying integrity and preventing recurring compromise."
        ),
    },

    # ==========================================
    # ISO/IEC 27001:2022 (Annex A)
    # ==========================================
    {
        "framework": "ISO",
        "version": "2022",
        "control_id": "ISO-A.5.15",
        "title": "Access Control",
        "type": "standard",
        "source": "ISO/IEC 27001:2022",
        "content_ref": "Annex A.5 Organizational Controls",
        "content": (
            "Rules to control physical and logical access to information and other associated assets shall be established "
            "and implemented based on business and information security requirements."
        ),
    },
    {
        "framework": "ISO",
        "version": "2022",
        "control_id": "ISO-A.5.18",
        "title": "Access Rights and Privileged Identities",
        "type": "standard",
        "source": "ISO/IEC 27001:2022",
        "content_ref": "Annex A.5 Organizational Controls",
        "content": (
            "Access rights to information and systems shall be provisioned, reviewed, modified, and removed in accordance "
            "with the organization's access control policy. High-privilege access must be strictly segregated."
        ),
    },
    {
        "framework": "ISO",
        "version": "2022",
        "control_id": "ISO-A.8.7",
        "title": "Protection Against Malware",
        "type": "standard",
        "source": "ISO/IEC 27001:2022",
        "content_ref": "Annex A.8 Technological Controls",
        "content": (
            "Protection against malware shall be implemented and supported by appropriate user awareness, "
            "centralized endpoint telemetry, and automated detection and quarantine mechanisms."
        ),
    },
    {
        "framework": "ISO",
        "version": "2022",
        "control_id": "ISO-A.8.8",
        "title": "Management of Technical Vulnerabilities",
        "type": "standard",
        "source": "ISO/IEC 27001:2022",
        "content_ref": "Annex A.8 Technological Controls",
        "content": (
            "Information about technical vulnerabilities of information systems in use shall be obtained, "
            "the organization's exposure to such vulnerabilities evaluated and appropriate measures taken."
        ),
    },
    {
        "framework": "ISO",
        "version": "2022",
        "control_id": "ISO-A.8.9",
        "title": "Configuration Management",
        "type": "standard",
        "source": "ISO/IEC 27001:2022",
        "content_ref": "Annex A.8 Technological Controls",
        "content": (
            "Configurations, including security configurations, of hardware, software, services and networks "
            "shall be established, documented, implemented, monitored and reviewed."
        ),
    },
    {
        "framework": "ISO",
        "version": "2022",
        "control_id": "ISO-A.8.13",
        "title": "Information Backup",
        "type": "standard",
        "source": "ISO/IEC 27001:2022",
        "content_ref": "Annex A.8 Technological Controls",
        "content": (
            "Backup copies of information, software and systems shall be maintained and regularly tested in "
            "accordance with the agreed topic-specific policy on backup."
        ),
    },
    {
        "framework": "ISO",
        "version": "2022",
        "control_id": "ISO-A.8.16",
        "title": "Monitoring Activities and Logging",
        "type": "standard",
        "source": "ISO/IEC 27001:2022",
        "content_ref": "Annex A.8 Technological Controls",
        "content": (
            "Networks, systems and applications shall be monitored for anomalous behavior and appropriate actions "
            "taken to evaluate potential information security incidents."
        ),
    },
    {
        "framework": "ISO",
        "version": "2022",
        "control_id": "ISO-A.8.20",
        "title": "Network Security and Boundary Segmentation",
        "type": "standard",
        "source": "ISO/IEC 27001:2022",
        "content_ref": "Annex A.8 Technological Controls",
        "content": (
            "Networks and network devices shall be secured, managed and controlled to protect information "
            "in systems and applications. Groups of information services, users and information systems shall be divided on networks."
        ),
    },
]
