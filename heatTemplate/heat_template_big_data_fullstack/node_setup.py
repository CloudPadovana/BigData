#!/usr/bin/python

import sys, os, os.path, re, traceback
import logging
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
    tplConfig.read("/etc/cloudveneto_node_setup.conf")

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

    mp_regex = r'[a-z0-9]+:[^:]+:[^\s]+'
    mount_points = re.findall(mp_regex, tplConfig.get("main", "mount_points"))

    for m_item in mount_points:
        try:
            tmpt = tuple(m_item.split(':'))
            os.makedirs(tmpt[2], 0777)
            check_call("mount -t %s %s %s" % tmpt, shell=True)
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

        with open("%s/kafka/config/server.properties" % workdir, "w") as kconf:
            kconf.write("broker.id=%d\n" % node_id)
            kconf.write("num.network.threads=3\n")
            kconf.write("num.io.threads=8\n")
            kconf.write("socket.send.buffer.bytes=102400\n")
            kconf.write("socket.receive.buffer.bytes=102400\n")
            kconf.write("socket.request.max.bytes=104857600\n")
            kconf.write("log.dirs=/var/lib/kafka/kafka-logs\n")
            kconf.write("num.partitions=1\n")
            kconf.write("num.recovery.threads.per.data.dir=1\n")
            kconf.write("offsets.topic.replication.factor=1\n")
            kconf.write("transaction.state.log.replication.factor=1\n")
            kconf.write("transaction.state.log.min.isr=1\n")
            kconf.write("log.retention.hours=168\n")
            kconf.write("log.segment.bytes=1073741824\n")
            kconf.write("log.retention.check.interval.ms=300000\n")
            kconf.write("zookeeper.connect=localhost:2181\n")
            kconf.write("zookeeper.connection.timeout.ms=6000\n")
            kconf.write("group.initial.rebalance.delay.ms=0\n")

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

    if "hadoop" in node_type:

        logging.info("Installing Spark")

        hdver = "2.9.1"

        if not node_id in hdfsIDs:
            raise Exception("Node id %d is not a hdfs node" % node_id)

        check_call("wget -O /tmp/hadoop-%s.tar.gz %s/hadoop-%s.tar.gz" % (hdver, repo_url, hdver), shell=True)
        check_call(runcmd % ("tar -C %s -zxf /tmp/hadoop-%s.tar.gz" % (workdir, hdver)), shell=True)
        os.rename("%s/hadoop-%s" % (workdir, hdver), "%s/hadoop" % workdir)

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

        os.makedirs("%s/datanode" % workdir, 0770)
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

        with open("%s/nifi/conf/nifi.properties" % workdir, "w") as nififile:
            nififile.write("nifi.administrative.yield.duration=30 sec\n")
            nififile.write("nifi.authorizer.configuration.file=%s/nifi/conf/authorizers.xml\n" % workdir)
            nififile.write("nifi.bored.yield.duration=10 millis\n")
            nififile.write("nifi.cluster.firewall.file=\n")
            nififile.write("nifi.cluster.flow.election.max.candidates=\n")
            nififile.write("nifi.cluster.flow.election.max.wait.time=5 mins\n")
            nififile.write("nifi.cluster.is.node=false\n")
            nififile.write("nifi.cluster.node.address=\n")
            nififile.write("nifi.cluster.node.connection.timeout=5 sec\n")
            nififile.write("nifi.cluster.node.event.history.size=25\n")
            nififile.write("nifi.cluster.node.max.concurrent.requests=100\n")
            nififile.write("nifi.cluster.node.protocol.max.threads=50\n")
            nififile.write("nifi.cluster.node.protocol.port=\n")
            nififile.write("nifi.cluster.node.protocol.threads=10\n")
            nififile.write("nifi.cluster.node.read.timeout=5 sec\n")
            nififile.write("nifi.cluster.protocol.heartbeat.interval=5 sec\n")
            nififile.write("nifi.cluster.protocol.is.secure=true\n")
            nififile.write("nifi.components.status.repository.buffer.size=1440\n")
            nififile.write("nifi.components.status.repository.implementation=")
            nififile.write("org.apache.nifi.controller.status.history.VolatileComponentStatusRepository\n")
            nififile.write("nifi.components.status.snapshot.frequency=1 min\n")
            nififile.write("nifi.content.claim.max.appendable.size=1 MB\n")
            nififile.write("nifi.content.claim.max.flow.files=100\n")
            nififile.write("nifi.content.repository.always.sync=false\n")
            nififile.write("nifi.content.repository.archive.enabled=true\n")
            nififile.write("nifi.content.repository.archive.max.retention.period=12 hours\n")
            nififile.write("nifi.content.repository.archive.max.usage.percentage=50%\n")
            nififile.write("nifi.content.repository.directory.default=%s/nifi/content_repository\n" % workdir)
            nififile.write("nifi.content.repository.implementation=")
            nififile.write("org.apache.nifi.controller.repository.FileSystemRepository\n")
            nififile.write("nifi.content.viewer.url=../nifi-content-viewer/\n")
            nififile.write("nifi.database.directory=./database_repository\n")
            nififile.write("nifi.documentation.working.directory=%s/nifi/work/docs/components\n" % workdir)
            nififile.write("nifi.flow.configuration.archive.dir=%s/nifi/conf/archive/\n" % workdir)
            nififile.write("nifi.flow.configuration.archive.enabled=true\n")
            nififile.write("nifi.flow.configuration.archive.max.count=\n")
            nififile.write("nifi.flow.configuration.archive.max.storage=500 MB\n")
            nififile.write("nifi.flow.configuration.archive.max.time=30 days\n")
            nififile.write("nifi.flow.configuration.file=./conf/flow.xml.gz\n")
            nififile.write("nifi.flowcontroller.autoResumeState=true\n")
            nififile.write("nifi.flowcontroller.graceful.shutdown.period=10 sec\n")
            nififile.write("nifi.flowfile.repository.always.sync=false\n")
            nififile.write("nifi.flowfile.repository.checkpoint.interval=2 mins\n")
            nififile.write("nifi.flowfile.repository.directory=%s/nifi/flowfile_repository\n" % workdir)
            nififile.write("nifi.flowfile.repository.implementation=")
            nififile.write("org.apache.nifi.controller.repository.WriteAheadFlowFileRepository\n")
            nififile.write("nifi.flowfile.repository.partitions=256\n")
            nififile.write("nifi.flowfile.repository.wal.implementation=")
            nififile.write("org.apache.nifi.wali.SequentialAccessWriteAheadLog\n")
            nififile.write("nifi.flowservice.writedelay.interval=500 ms\n")
            nififile.write("nifi.h2.url.append=;LOCK_TIMEOUT=25000;WRITE_DELAY=0;AUTO_SERVER=FALSE\n")
            nififile.write("nifi.kerberos.krb5.file=\n")
            nififile.write("nifi.kerberos.service.keytab.location=\n")
            nififile.write("nifi.kerberos.service.principal=\n")
            nififile.write("nifi.kerberos.spnego.authentication.expiration=12 hours\n")
            nififile.write("nifi.kerberos.spnego.keytab.location=\n")
            nififile.write("nifi.kerberos.spnego.principal=\n")
            nififile.write("nifi.login.identity.provider.configuration.file=")
            nififile.write("%s/nifi/conf/login-identity-providers.xml\n" % workdir)
            nififile.write("nifi.nar.library.directory=%s/nifi/lib\n" % workdir)
            nififile.write("nifi.nar.working.directory=%s/nifi/work/nar/\n" % workdir)
            nififile.write("nifi.provenance.repository.always.sync=false\n")
            nififile.write("nifi.provenance.repository.buffer.size=100000\n")
            nififile.write("nifi.provenance.repository.compress.on.rollover=true\n")
            nififile.write("nifi.provenance.repository.concurrent.merge.threads=2\n")
            nififile.write("nifi.provenance.repository.debug.frequency=1_000_000\n")
            nififile.write("nifi.provenance.repository.directory.default=")
            nififile.write("%s/nifi/provenance_repository\n" % workdir)
            nififile.write("nifi.provenance.repository.encryption.key=\n")
            nififile.write("nifi.provenance.repository.encryption.key.id=\n")
            nififile.write("nifi.provenance.repository.encryption.key.provider.implementation=\n")
            nififile.write("nifi.provenance.repository.encryption.key.provider.location=\n")
            nififile.write("nifi.provenance.repository.implementation=")
            nififile.write("org.apache.nifi.provenance.PersistentProvenanceRepository\n")
            nififile.write("nifi.provenance.repository.indexed.attributes=\n")
            nififile.write("nifi.provenance.repository.indexed.fields=")
            nififile.write("EventType, FlowFileUUID, Filename, ProcessorID, Relationship\n")
            nififile.write("nifi.provenance.repository.index.shard.size=500 MB\n")
            nififile.write("nifi.provenance.repository.index.threads=2\n")
            nififile.write("nifi.provenance.repository.journal.count=16\n")
            nififile.write("nifi.provenance.repository.max.attribute.length=65536\n")
            nififile.write("nifi.provenance.repository.max.storage.size=1 GB\n")
            nififile.write("nifi.provenance.repository.max.storage.time=24 hours\n")
            nififile.write("nifi.provenance.repository.query.threads=2\n")
            nififile.write("nifi.provenance.repository.rollover.size=100 MB\n")
            nififile.write("nifi.provenance.repository.rollover.time=30 secs\n")
            nififile.write("nifi.provenance.repository.warm.cache.frequency=1 hour\n")
            nififile.write("nifi.queue.backpressure.count=10000\n")
            nififile.write("nifi.queue.backpressure.size=1 GB\n")
            nififile.write("nifi.queue.swap.threshold=20000\n")
            nififile.write("nifi.remote.contents.cache.expiration=30 secs\n")
            nififile.write("nifi.remote.input.host=\n")
            nififile.write("nifi.remote.input.http.enabled=true\n")
            nififile.write("nifi.remote.input.http.transaction.ttl=30 sec\n")
            nififile.write("nifi.remote.input.secure=true\n")
            nififile.write("nifi.remote.input.socket.port=\n")
            nififile.write("nifi.security.keyPasswd=%s\n" % rootpwd)
            nififile.write("nifi.security.keystore=%s/nifi/conf/service.jks\n" % workdir)
            nififile.write("nifi.security.keystorePasswd=%s\n" % rootpwd)
            nififile.write("nifi.security.keystoreType=JKS\n")
            nififile.write("nifi.security.needClientAuth=false\n")
            nififile.write("nifi.security.ocsp.responder.certificate=\n")
            nififile.write("nifi.security.ocsp.responder.url=\n")
            nififile.write("nifi.security.truststore=/etc/pki/java/cacerts\n")
            nififile.write("nifi.security.truststorePasswd=changeit\n")
            nififile.write("nifi.security.truststoreType=JKS\n")
            nififile.write("nifi.security.user.authorizer=managed-authorizer\n")
            nififile.write("nifi.security.user.knox.audiences=\n")
            nififile.write("nifi.security.user.knox.cookieName=hadoop-jwt\n")
            nififile.write("nifi.security.user.knox.publicKey=\n")
            nififile.write("nifi.security.user.knox.url=\n")
            nififile.write("nifi.security.user.login.identity.provider=\n")
            nififile.write("nifi.security.user.oidc.client.id=%s\n" % oidc_id)
            nififile.write("nifi.security.user.oidc.client.secret=%s\n" % oidc_sec)
            nififile.write("nifi.security.user.oidc.connect.timeout=5 secs\n")
            nififile.write("nifi.security.user.oidc.discovery.url=%s\n" % oidc_idp)
            nififile.write("nifi.security.user.oidc.preferred.jwsalgorithm=\n")
            nififile.write("nifi.security.user.oidc.read.timeout=5 secs\n")
            nififile.write("nifi.sensitive.props.additional.keys=\n")
            nififile.write("nifi.sensitive.props.algorithm=PBEWITHMD5AND256BITAES-CBC-OPENSSL\n")
            nififile.write("nifi.sensitive.props.key=%s\n" % rootpwd)
            nififile.write("nifi.sensitive.props.key.protected=\n")
            nififile.write("nifi.sensitive.props.provider=BC\n")
            nififile.write("nifi.state.management.configuration.file=")
            nififile.write("%s/nifi/conf/state-management.xml\n" % workdir)
            nififile.write("nifi.state.management.embedded.zookeeper.properties=")
            nififile.write("%s/nifi/conf/zookeeper.properties\n" % workdir)
            nififile.write("nifi.state.management.embedded.zookeeper.start=false\n")
            nififile.write("nifi.state.management.provider.cluster=zk-provider\n")
            nififile.write("nifi.state.management.provider.local=local-provider\n")
            nififile.write("nifi.swap.in.period=5 sec\n")
            nififile.write("nifi.swap.in.threads=1\n")
            nififile.write("nifi.swap.manager.implementation=")
            nififile.write("org.apache.nifi.controller.FileSystemSwapManager\n")
            nififile.write("nifi.swap.out.period=5 sec\n")
            nififile.write("nifi.swap.out.threads=4\n")
            nififile.write("nifi.templates.directory=%s/nifi/conf/templates\n" % workdir)
            nififile.write("nifi.ui.autorefresh.interval=30 sec\n")
            nififile.write("nifi.ui.banner.text=\n")
            nififile.write("nifi.variable.registry.properties=\n")
            nififile.write("nifi.web.http.host=\n")
            nififile.write("nifi.web.http.network.interface.default=\n")
            nififile.write("nifi.web.http.port=\n")
            nififile.write("nifi.web.https.host=0.0.0.0\n")
            nififile.write("nifi.web.https.network.interface.default=\n")
            nififile.write("nifi.web.https.port=8443\n")
            nififile.write("nifi.web.jetty.threads=200\n")
            nififile.write("nifi.web.jetty.working.directory=%s/nifi/work/jetty\n" % workdir)
            nififile.write("nifi.web.max.header.size=16 KB\n")
            nififile.write("nifi.web.proxy.context.path=\n")
            nififile.write("nifi.web.proxy.host=\n")
            nififile.write("nifi.web.war.directory=%s/nifi/lib\n" % workdir)
            nififile.write("nifi.zookeeper.auth.type=\n")
            nififile.write("nifi.zookeeper.connect.string=\n")
            nififile.write("nifi.zookeeper.connect.timeout=3 secs\n")
            nififile.write("nifi.zookeeper.kerberos.removeHostFromPrincipal=\n")
            nififile.write("nifi.zookeeper.kerberos.removeRealmFromPrincipal=\n")
            nififile.write("nifi.zookeeper.root.node=/nifi\n")
            nififile.write("nifi.zookeeper.session.timeout=3 secs\n")

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

