# Heat Templates 

#### Table of Contents

1. [Overview](#overview)
2. [Heat](#Heat)
   * [Template creation](#TemplateCreation) 
3. [Template with some description](#tested-on)

## Overview

In this directory you can find some heat templates to deploy different clusters in the one specific project in the Open Stack cloud areapadovana or in other Openstack cloud. You have to set some parameters to allow the template works properly. To use theese templates you need  the heat component of Openstack. 

## Heat

Heat is the main project in the OpenStack Orchestration program. It implements an orchestration engine to launch multiple composite cloud applications based on templates in the form of text files that can be treated like code. A native Heat template format is evolving, but Heat also endeavours to provide compatibility with the AWS CloudFormation template format, so that many existing CloudFormation templates can be launched on OpenStack. Heat provides both an OpenStack-native ReST API and a CloudFormation-compatible Query API. 
[More Docuementation](https://wiki.openstack.org/wiki/Heat)

### Template creation

HOT is a template format supported by the heat, along with the other template format, i.e. the Heat CloudFormation-compatible format (CFN). This guide is targeted towards template authors and explains how to write HOT templates based on examples. A detailed specification of HOT can be found at Heat Orchestration Template (HOT) specification
[More Docuementation](https://docs.openstack.org/heat/pike/template_guide/hot_guide.html)

## Template with some description

* *heat_template_MesosMarathonChronos-4nodes.txt*
This file contains the template which has been able to create a cluster of 4 nodes with 3 Mesos masters in HA using Zookeeper. In all of the firt three nodes mesos-master, marathon anf chronos will be installed and configured. The fouth node is just a meos slave. You can create other template with many slaves and attach theese slaves to the master in this template.

In this template you need to set properly the paramters:
 * image to use (a CentOS7 image or similar distro with yum/rpm as packages distribution)
 * key name user ( the name of ssh key deployed in Openstack for the specific user)
 * the falvor to use (tipical small or medium one)
 * the tenant or project id of the network
 * the tenant or project id of the subnetwork
 * the ip in the subnetwork (theese have to be set because mesos need to know all the nodes in the cluster, so also if you add slaves the best things is to add nodename and relative ip in /etc/hosts of all nodes in the cluster)

The template when finish the deploy gives as output the root password for access to all nodes in the cluster.

* *heat_template_big_data_PD-Hadoop-Spark-CMS.txt*

This file contains the template which has been able to create a cluster of 6 nodes with 1 Hadoop and Spark master. In all of the other nodes the Spark and Hadoop slaves will be deployed.

In this template you need to set properly the paramters:
 * image to use (a CentOS7 image or similar)
 * key name user ( the name of ssh key deployed in Openstack for the specific user)
 * the falvor to use (tipical small or medium one)
 * the tenant or project id of the network
 * the tenant or project id of the subnetwork
 * the ip in the subnetwork (theese have to be set because hadoop and spark need to know all the nodes in the cluster, so also if you add slaves the best things is to add nodename and relative ip in /etc/hosts of all nodes in the cluster)

The template when finish the deploy gives as output the root and the hadoop passwords for access to all nodes in the cluster with root user instead of hadoop user. Hadoop user is useful to use hdfs command (the enviroment will be properly set for this user)

* *heat_template_big_data_PD-Hadoop.txt* *heat_template_big_data_PD-Hadoop_with_Volumes.txt*

Theese two template create just and Hadoop cluster with yarn and hdfs. The second one use cinder volume to store data, the first one use just the space in the ephemeral disk of the virtual machine.

