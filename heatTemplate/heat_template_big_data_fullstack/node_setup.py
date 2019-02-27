#!/usr/bin/python

import sys, os, os.path, re, traceback
import logging
import json
from subprocess import check_call
from ConfigParser import ConfigParser

try:
    logging.basicConfig(
        filename='/var/log/cloudveneto_heat.log',
        format= "%(asctime)s %(levelname)s %(message)s",
        level=logging.DEBUG
    )
except Exception, conf_log_err:
    logging.basicConfig(stream=sys.stderr)

try:

    logging.info("Configuring ssh")

    tplConfig = ConfigParser()
    tplConfig.read("/etc/cloudveneto/node_setup.conf")

    host_prefix = tplConfig.get("main", "host_prefix")
    node_id = int(tplConfig.get("main", "node_id"))
    lan_ippre = tplConfig.get("main", "lan_ippre")
    nameservers = tplConfig.get("main", "nameservers")
    node_type = re.split("\s+", tplConfig.get("main", "node_type"))
    rootpwd = tplConfig.get("main", "rootpwd")
    admin_id = tplConfig.get("main", "admin_id")
    
    oidc_id = tplConfig.get("main", "oidc_id")
    if oidc_id.lower() == "undefined":
        oidc_id = ""
    oidc_sec = tplConfig.get("main", "oidc_sec")
    if oidc_sec.lower() == "undefined":
        oidc_sec = ""
    oidc_idp = tplConfig.get("main", "oidc_idp")
    if oidc_idp.lower() == "undefined":
        oidc_idp = ""
    
    servername = tplConfig.get("main", "servername").strip()
    if not servername or servername == "undefined":
        servername = "%s-%d.pd.infn.it" % (host_prefix, node_id)

    workdir = "/opt/bigdata"
    bguser = "bigdatausr"

    kafkaIDs = map(lambda x: int(x), re.findall(r'\d+', tplConfig.get("main", "kafka_ids")))
    sparkIDs = map(lambda x: int(x), re.findall(r'\d+', tplConfig.get("main", "spark_ids")))
    hdfsIDs = map(lambda x: int(x), re.findall(r'\d+', tplConfig.get("main", "hdfs_ids")))
    wnIDs = map(lambda x: int(x), re.findall(r'\d+', tplConfig.get("main", "wn_ids")))
    allIDs = set(kafkaIDs) | set(sparkIDs) | set(hdfsIDs) | set(wnIDs)

    if len(hdfsIDs) == 0:
        hdfsIDs = sparkIDs

    repo_url = "http://artifacts.pd.infn.it/packages/SMACT/misc"

    check_call("hostnamectl set-hostname %s" % servername, shell=True)

    with open("/etc/hosts", "w") as hostsfile:
        hostsfile.write("127.0.0.1 localhost.pd.infn.it localhost\n")
        hostsfile.write("::1       localhost.pd.infn.it localhost\n")
        for item in allIDs:
            tmpn = "%s-%d" % (host_prefix, item)
            hostsfile.write("%s.%d %s.pd.infn.it %s\n" % (lan_ippre, item, tmpn, tmpn))

    with open("/etc/ssh/shosts.equiv", "w") as equivfile:
        for item in allIDs:
            equivfile.write("%s-%d.pd.infn.it\n" % (host_prefix, item))

    with open("/etc/resolv.conf", "w") as resolvfile:
        resolvfile.write("search pd.infn.it\n")
        resolvfile.write("nameserver %s\n" % nameservers)

    with open("/etc/ssh/sshd_config", "a") as sshdfile:
        sshdfile.write("# workaround\n")
        sshdfile.write("HostbasedAuthentication yes\n")
        sshdfile.write("IgnoreUserKnownHosts yes\n")
        sshdfile.write("IgnoreRhosts yes\n")

    with open("/etc/ssh/ssh_config", "w") as sshfile:
        sshfile.write("Host *\n")
        sshfile.write("    HostbasedAuthentication yes\n")
        sshfile.write("    EnableSSHKeysign yes\n")
        sshfile.write("    GSSAPIAuthentication no\n")
        sshfile.write("    ForwardX11Trusted yes\n")
        sshfile.write("    SendEnv LANG LC_CTYPE LC_NUMERIC LC_TIME LC_COLLATE LC_MONETARY LC_MESSAGES\n")
        sshfile.write("    SendEnv LC_PAPER LC_NAME LC_ADDRESS LC_TELEPHONE LC_MEASUREMENT\n")
        sshfile.write("    SendEnv LC_IDENTIFICATION LC_ALL LANGUAGE\n")
        sshfile.write("    SendEnv XMODIFIERS\n")

    with open("/etc/sysctl.conf", "a") as sysfile:
        sysfile.write("net.ipv6.conf.all.disable_ipv6 = 1\n")
        sysfile.write("net.ipv6.conf.default.disable_ipv6 = 1\n")

    check_call("useradd -d %s %s" % (workdir, bguser), shell=True)
    runcmd = "runuser -s /bin/bash -c \"%s\" -- " + bguser

    #####################################################################################
    # Volumes setup
    #####################################################################################

    mp_regex = r'[a-z]+:[a-z0-9]+:[^:]+:[^\s]+'
    mount_points = re.findall(mp_regex, tplConfig.get("main", "mount_points"))

    for m_item in mount_points:
        try:
            tmpl = m_item.split(':')
            if tmpl.pop(0) == 'format':
                check_call("mkfs -t %s %s" % (tmpl[0], tmpl[1]), shell=True)
            os.makedirs(tmpl[2])
            check_call("mount -t %s %s %s" % tuple(tmpl), shell=True)
            check_call("chmod 777 %s" % tmpl[2], shell=True)
        except:
            logging.exception("Cannot mount %s\n" % repr(tmpt))

    #####################################################################################
    # Kafka setup
    #####################################################################################

    if "kafka" in node_type:

        logging.info("Installing Kafka")

        kafkaver = "2.11-1.1.0"

        if not node_id in kafkaIDs:
            raise Exception("Node id %d is not a kafka node")

        check_call("wget -O /tmp/kafka_%s.tgz %s/kafka_%s.tgz" % (kafkaver, repo_url, kafkaver), shell=True)
        check_call("tar -C %s -zxf /tmp/kafka_%s.tgz" % (workdir, kafkaver), shell=True)
        os.rename("%s/kafka_%s" % (workdir, kafkaver), "%s/kafka" % workdir)
        for d_item in [ "/var/lib/kafka", "/var/lib/kafka/kafka-logs", "/var/cache/zookeeper" ]:
            os.makedirs(d_item, 0770)
            check_call("chown %s.%s %s" % (bguser, bguser, d_item), shell=True)

        with open("/etc/cloudveneto/kafka_config.json") as kconffile:
            kafka_cfg = json.load(kconffile)
        kafka_cfg["broker.id"] = str(node_id)
        kafka_cfg["log.dirs"] = "/var/lib/kafka/kafka-logs"

        with open("%s/kafka/config/server.properties" % workdir, "w") as kconf:
            for kafka_pair in kafka_cfg.items():
                kconf.write("%s=%s\n" % kafka_pair)

        with open("%s/kafka/config/zookeeper.properties" % workdir, "w") as zconf:
            zconf.write("dataDir=/var/cache/zookeeper\n")
            zconf.write("clientPort=2181\n")
            zconf.write("tickTime=2000\n")
            zconf.write("initLimit=5\n")
            zconf.write("syncLimit=2\n")
            for item in kafkaIDs:
                zconf.write("server.%d=%s-%d.pd.infn.it:2888:3888\n" % (item, host_prefix, item))

        with open("/var/cache/zookeeper/myid", "w") as idfile:
            idfile.write("%d\n" % node_id)

        with open("/usr/lib/systemd/system/zookeeper.service", "w") as zsrvfile:
            zsrvfile.write("[Unit]\nDescription=Zookeeper service\n\n")
            zsrvfile.write("[Service]\nExecStart=/usr/sbin/runuser -s /bin/bash ")
            zsrvfile.write("-c \"%s/kafka/bin/zookeeper-server-start.sh " % workdir)
            zsrvfile.write("%s/kafka/config/zookeeper.properties\" -- %s\n" % (workdir, bguser))
            zsrvfile.write("ExecStop=/usr/sbin/runuser -s /bin/bash ")
            zsrvfile.write("-c \"%s/kafka/bin/zookeeper-server-stop.sh\" -- %s\n\n" % (workdir, bguser))
            zsrvfile.write("[Install]\nWantedBy=multi-user.target\n")

        with open("/usr/lib/systemd/system/kafka.service", "w") as ksrvfile:
            ksrvfile.write("[Unit]\nDescription=Kafka broker\n")
            ksrvfile.write("Wants=zookeeper.service\nAfter=zookeeper.service\n\n")
            ksrvfile.write("[Service]\nExecStart=/usr/sbin/runuser -s /bin/bash ")
            ksrvfile.write("-c \"%s/kafka/bin/kafka-server-start.sh " %workdir)
            ksrvfile.write("%s/kafka/config/server.properties\" -- %s\n"% (workdir, bguser))
            ksrvfile.write("ExecStop=/usr/sbin/runuser -s /bin/bash ")
            ksrvfile.write("-c \"%s/kafka/bin/kafka-server-start.sh\" -- %s\n\n" % (workdir, bguser))
            ksrvfile.write("[Install]\nWantedBy=multi-user.target\n")

        with open("/etc/bashrc", "a") as rcfile:
            rcfile.write("export PATH=$PATH:%s/kafka/bin/\n" % workdir) 

    #####################################################################################
    # Spark and HDFS setup
    #####################################################################################

    spkhome = workdir + "/spark"
    hdhome = workdir + "/hadoop"

    if "hadoop" in node_type or "spark" in node_type:
        corecfg =  "<configuration>\n"
        corecfg += "  <property>\n"
        corecfg += "    <name>fs.defaultFS</name>\n"
        corecfg += "    <value>hdfs://%s-%d.pd.infn.it:9000/</value>\n" % (host_prefix, hdfsIDs[0])
        corecfg += "  </property>\n"
        corecfg += "</configuration>\n"

        hdfscfg =  "<configuration>\n"
        hdfscfg += "  <property><name>dfs.replication</name><value>1</value></property>\n"
        hdfscfg += "  <property><name>dfs.permissions</name><value>false</value></property>\n"
        hdfscfg += "  <property><name>dfs.datanode.data.dir</name>"
        hdfscfg += "<value>%s/datanode</value></property>\n" % workdir
        hdfscfg += "  <property><name>dfs.namenode.name.dir</name>"
        hdfscfg += "<value>%s/namenode</value></property>\n" % workdir
        hdfscfg += "  <property> <name>dfs.secondary.http.address</name>"
        hdfscfg += "<value>%s.%d:50090</value></property>\n" % (lan_ippre, hdfsIDs[0])
        hdfscfg += "</configuration>\n"

        with open("/etc/profile.d/hadoop.sh", "w") as proffile:
            proffile.write("export JAVA_HOME=/usr/lib/jvm/jre-1.8.0-openjdk\n")
            proffile.write("export JRE_HOME=/usr/lib/jvm/jre-1.8.0-openjdk/jre\n")
            proffile.write("export HADOOP_PREFIX=%s\n" % hdhome)
            proffile.write("export HADOOP_HOME=%s\n" % hdhome)
            proffile.write("export HADOOP_COMMON_HOME=%s\n" % hdhome)
            proffile.write("export HADOOP_CONF_DIR=%s/etc/hadoop\n" % hdhome)
            proffile.write("export HADOOP_HDFS_HOME=%s\n" % hdhome)
            proffile.write("export HADOOP_MAPRED_HOME=%s\n" % hdhome)
            proffile.write("export HADOOP_YARN_HOME=%s\n" % hdhome)
            proffile.write("export PYTHONPATH=$PYTHONPATH:%s/python\n" % spkhome)
            proffile.write("export PATH=$PATH:%s/bin:%s/sbin\n" % (hdhome, hdhome))
            proffile.write("export PATH=$PATH:%s/bin:%s/sbin\n" % (spkhome, spkhome))

    if "hadoop" in node_type:

        logging.info("Installing Spark")

        hdver = "2.9.1"

        if not node_id in hdfsIDs:
            raise Exception("Node id %d is not a hdfs node" % node_id)

        check_call("wget -O /tmp/hadoop-%s.tar.gz %s/hadoop-%s.tar.gz" % (hdver, repo_url, hdver), shell=True)
        check_call(runcmd % ("tar -C %s -zxf /tmp/hadoop-%s.tar.gz" % (workdir, hdver)), shell=True)
        os.rename("%s/hadoop-%s" % (workdir, hdver), "%s/hadoop" % workdir)

        if not os.path.exists("%s/datanode" % workdir):
            os.makedirs("%s/datanode" % workdir, 0770)
        if not os.path.exists("%s/namenode" % workdir):
            os.makedirs("%s/namenode" % workdir, 0770)
        check_call("chown %s.%s %s/datanode %s/namenode" % (bguser, bguser, workdir, workdir), shell=True)

        with open("%s/etc/hadoop/core-site.xml" % hdhome, "w") as corefile:
            corefile.write(corecfg)

        with open("%s/etc/hadoop/hdfs-site.xml" % hdhome, "w") as hdfscfile:
            hdfscfile.write(hdfscfg)

        with open("%s/etc/hadoop/mapred-site.xml" % hdhome, "w") as mrcfile:
            mrcfile.write("<configuration>\n")
            mrcfile.write("  <property><name>mapreduce.framework.name</name><value>yarn</value></property>\n")
            mrcfile.write("</configuration>\n")

        with open("%s/etc/hadoop/yarn-site.xml" % hdhome, "w") as yarnfile:
            yarnfile.write("<configuration>\n")
            yarnfile.write("  <property><name>yarn.resourcemanager.hostname</name>")
            yarnfile.write("<value>%s-%d</value></property>\n" % (host_prefix, hdfsIDs[0]))
            yarnfile.write("  <property><name>yarn.nodemanager.hostname</name>")
            yarnfile.write("<value>%s-%d</value></property>\n" % (host_prefix, hdfsIDs[0]))
            yarnfile.write("  <property><name>yarn.nodemanager.aux-services</name>")
            yarnfile.write("<value>mapreduce_shuffle</value></property>\n")
            yarnfile.write("</configuration>\n")

        with open("%s/etc/hadoop/slaves" % hdhome, "w") as slavefile:
            for item in hdfsIDs[1:]:
                slavefile.write("%s-%d.pd.infn.it\n" % (host_prefix, item))

        if node_id == hdfsIDs[0]:
            check_call(runcmd % ("JAVA_HOME=/usr/lib/jvm/jre-1.8.0-openjdk %s/bin/hdfs namenode -format" % hdhome),
                 shell=True)

    if "spark" in node_type:

        spkver = "2.3.2"
        spk_wport = 6066

        if not node_id in sparkIDs:
            raise Exception("Node id %d is not a spark node" % node_id)

        check_call("wget -O /tmp/spark-%s.tar.gz %s/spark-%s-bin-without-hadoop.tgz" % (spkver, repo_url, spkver), shell=True)
        check_call(runcmd % ("tar -C %s -zxf /tmp/spark-%s.tar.gz" % (workdir, spkver)), shell=True)
        os.rename("%s/spark-%s-bin-without-hadoop" % (workdir, spkver), "%s/spark" % workdir)

        with open("%s/conf/spark-env.sh" % spkhome, "w") as spenvfile:
            spenvfile.write("export SPARK_DIST_CLASSPATH=")
            if "hadoop" in node_type:
                spenvfile.write("$(%s/bin/hadoop --config %s/etc/hadoop classpath)\n" % (hdhome, hdhome))
            spenvfile.write("export SPARK_WORKER_PORT=%d\n" % spk_wport)

        with open("%s/conf/slaves" % spkhome, "w") as slavefile:
            for item in sparkIDs[1:]:
                slavefile.write("%s-%d.pd.infn.it\n" % (host_prefix, item))

    #####################################################################################
    # Nifi setup
    #####################################################################################

    if "nifi" in node_type:

        logging.info("Installing NiFi")

        nifiver = "1.7.1"

        check_call("wget -O /tmp/nifi-%s.tar.gz %s/nifi-%s-bin.tar.gz" % (nifiver, repo_url, nifiver), shell=True)
        check_call(runcmd % ("tar -C %s -zxf /tmp/nifi-%s.tar.gz" % (workdir, nifiver)), shell=True)
        os.rename("%s/nifi-%s" % (workdir, nifiver), "%s/nifi" % workdir)

        with open("/etc/cloudveneto/nifi_config.json") as nificonffile:
            nifi_cfg = json.load(nificonffile)

        nifi_cfg["authorizer.configuration.file"] = "%s/nifi/conf/authorizers.xml" % workdir
        nifi_cfg["content.repository.directory.default"] = "%s/nifi/content_repository" % workdir
        nifi_cfg["documentation.working.directory"] = "%s/nifi/work/docs/components" % workdir
        nifi_cfg["flow.configuration.archive.dir"] = "%s/nifi/conf/archive/" % workdir
        nifi_cfg["flowfile.repository.directory"] = "%s/nifi/flowfile_repository" % workdir
        nifi_cfg["login.identity.provider.configuration.file"] = "%s/nifi/conf/login-identity-providers.xml" % workdir
        nifi_cfg["nar.library.directory"] = "%s/nifi/lib" % workdir
        nifi_cfg["nar.working.directory"] = "%s/nifi/work/nar/" % workdir
        nifi_cfg["provenance.repository.directory.default"] = "%s/nifi/provenance_repository" % workdir
        nifi_cfg["security.keystore"] = "%s/nifi/conf/service.jks" % workdir
        nifi_cfg["state.management.configuration.file"] = "%s/nifi/conf/state-management.xml" % workdir
        nifi_cfg["state.management.embedded.zookeeper.properties"] = "%s/nifi/conf/zookeeper.properties" % workdir
        nifi_cfg["templates.directory"] = "%s/nifi/conf/templates" % workdir
        nifi_cfg["web.jetty.working.directory"] = "%s/nifi/work/jetty" % workdir
        nifi_cfg["web.war.directory"] = "%s/nifi/lib" % workdir
        nifi_cfg["security.keyPasswd"] = rootpwd
        nifi_cfg["security.keystorePasswd"] = rootpwd
        nifi_cfg["security.user.oidc.client.id"] = oidc_id
        nifi_cfg["security.user.oidc.client.secret"] = oidc_sec
        nifi_cfg["security.user.oidc.discovery.url"] = oidc_idp
        nifi_cfg["sensitive.props.key"] = rootpwd

        nifi_cfg["components.status.repository.implementation"] = \
            "org.apache.nifi.controller.status.history.VolatileComponentStatusRepository"
        nifi_cfg["content.repository.implementation"] = \
            "org.apache.nifi.controller.repository.FileSystemRepository"
        nifi_cfg["flowfile.repository.implementation"] = \
            "org.apache.nifi.controller.repository.WriteAheadFlowFileRepository"
        nifi_cfg["flowfile.repository.wal.implementation"] = \
            "org.apache.nifi.wali.SequentialAccessWriteAheadLog"
        nifi_cfg["provenance.repository.implementation"] = \
            "org.apache.nifi.provenance.PersistentProvenanceRepository"
        nifi_cfg["swap.manager.implementation"] = \
            "org.apache.nifi.controller.FileSystemSwapManager"
        nifi_cfg["content.viewer.url"] = "../nifi-content-viewer/"
        nifi_cfg["database.directory"] = "./database_repository"
        nifi_cfg["flow.configuration.file"] = "./conf/flow.xml.gz"

        with open("%s/nifi/conf/nifi.properties" % workdir, "w") as nififile:
            for nifi_cpair in nifi_cfg.items():
                nififile.write("nifi.%s=%s\n" % nifi_cpair)

        with open("%s/nifi/conf/authorizers.xml" % workdir, "w") as authfile:
            authfile.write("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n")
            authfile.write("<authorizers>\n")
            authfile.write("  <userGroupProvider>\n")
            authfile.write("    <identifier>file-user-group-provider</identifier>\n")
            authfile.write("    <class>org.apache.nifi.authorization.FileUserGroupProvider</class>\n")
            authfile.write("    <property name=\"Users File\">./conf/users.xml</property>\n")
            authfile.write("    <property name=\"Legacy Authorized Users File\"></property>\n")
            authfile.write("    <property name=\"Legacy Authorized Users File\"></property>\n")
            authfile.write("    <property name=\"Legacy Authorized Users File\"></property>\n")
            authfile.write("    <property name=\"Legacy Authorized Users File\"></property>\n")
            authfile.write("    <property name=\"Initial User Identity 1\">%s</property>\n" % admin_id)
            authfile.write("  </userGroupProvider>\n")
            authfile.write("  <accessPolicyProvider>\n")
            authfile.write("    <identifier>file-access-policy-provider</identifier>\n")
            authfile.write("    <class>org.apache.nifi.authorization.FileAccessPolicyProvider</class>\n")
            authfile.write("    <property name=\"User Group Provider\">file-user-group-provider</property>\n")
            authfile.write("    <property name=\"Authorizations File\">./conf/authorizations.xml</property>\n")
            authfile.write("    <property name=\"Initial Admin Identity\">%s</property>\n" % admin_id)
            authfile.write("    <property name=\"Legacy Authorized Users File\"></property>\n")
            authfile.write("    <property name=\"Node Identity 1\"></property>\n")
            authfile.write("  </accessPolicyProvider>\n")
            authfile.write("  <authorizer>\n")
            authfile.write("    <identifier>managed-authorizer</identifier>\n")
            authfile.write("    <class>org.apache.nifi.authorization.StandardManagedAuthorizer</class>\n")
            authfile.write("    <property name=\"Access Policy Provider\">file-access-policy-provider</property>\n")
            authfile.write("   </authorizer>\n")
            authfile.write("</authorizers>\n")

        with open("%s/nifi/conf/hdfs-core-site.xml" % workdir, "w") as corefile:
            corefile.write(corecfg)

        with open("%s/nifi/conf/hdfs-site.xml" % workdir, "w") as hdfscfile:
            hdfscfile.write(hdfscfg)

    #####################################################################################
    # ML setup
    #####################################################################################

    if "ml" in node_type:

        bdlver = "0.7.0"

        logging.info("Installing ML packages")

        check_call("wget -O /tmp/bigdl-%s.tar.gz %s/bigdl-%s.tar.gz" % (bdlver, repo_url, bdlver), shell=True)
        check_call(runcmd % ("tar -C %s -zxf /tmp/bigdl-%s.tar.gz" % (workdir, bdlver)), shell=True)
        os.rename("%s/bigdl-%s" % (workdir, bdlver), "%s/bigdl" % workdir)

        with open("/etc/profile.d/bigdl.sh", "w") as prfile:
            prfile.write("export SPARK_HOME=%s/spark\n" % workdir)
            prfile.write("export BIGDL_HOME=%s/bigdl\n" % workdir)
            prfile.write("export PATH=$PATH:%s/bigdl/bin" % workdir)

        extrapkgs = "python-devel python2-pip python2-py4j gcc cmake hdf5-devel"
        #extrapkgs += "root root-tmva python2-root"
        check_call("yum -q -y install %s" % extrapkgs, shell=True)

        check_call([sys.executable, '-m', 'pip', 'install', '-q', '-U', 'pip'])

        c_args = [sys.executable, '-m', 'pip', 'install', '-q', '-U',
          'scikit-learn', 'scikit-image', 'pandas',
          'seaborn', 'tables', 'lime', 'graphviz'
        ]
        # 'root-pandas', 'rootpy', 'root_numpy'
        check_call(c_args)

    logging.info("Installation completed")

except:
    # TODO use signal or wc for stacktrace output
    #etype, evalue, etraceback = sys.exc_info()
    logging.exception("Execution error")

