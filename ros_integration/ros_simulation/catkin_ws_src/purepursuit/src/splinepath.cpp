/*
 * @Author: PurePursuit example authors
 * @Date: 2021-09-19 19:51:13
 * @LastEditTime: 2021-09-28 21:57:23
 * @LastEditors: Open-source release cleanup
 * @Description: In User Settings Edit
 * @FilePath: /ros/src/pathplay/src/pathload.cpp
 */
#include <geometry_msgs/PoseStamped.h>
#include <geometry_msgs/Quaternion.h>
#include <nav_msgs/Path.h>
#include <ros/ros.h>
#include <std_msgs/String.h>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "cpprobotics_types.h"
#include "cubic_spline.h"

using namespace std;

struct Pose
{
    double x;
    double y;
};

void saveCsvFile(std::string file_name, std::vector<Pose> path)
{
    std::ofstream outfile;
    outfile.open(file_name.c_str(), std::ios::trunc);
    outfile << "x"
        << ","
        << "y"
        << ","
        << "num" << std::endl;
    int num_count = 0;
    for (int i = 0; i < path.size(); ++i)
    {
        outfile << path.at(i).x << "," << path.at(i).y << "," << num_count << std::endl;
        num_count++;
    }
    outfile.close();
}

int main(int argc, char **argv) {
  ros::init(argc, argv, "spline");

  ros::NodeHandle sp;
  ros::Publisher path_pubs_ =
      sp.advertise<nav_msgs::Path>("splinepoints", 1000, true);
  // ros::Rate loop_rate(10);
  nav_msgs::Path now_path;

  now_path.header.frame_id = "world";
  // Set timestamp
  now_path.header.stamp = ros::Time::now();
  geometry_msgs::PoseStamped pose;
  pose.header.stamp = ros::Time::now();
  // Set reference frame
  pose.header.frame_id = "world";

  cpprobotics::Vec_f wx({0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0});
  cpprobotics::Vec_f wy({0.0, 10.0, 0.0, -10.0, 0.0, 10.0, 0.0});

  cpprobotics::Spline2D csp_obj(wx, wy);

  float sNum = csp_obj.s.back();
  ROS_INFO("sNum is : %f !! ", sNum);
  vector<Pose> poses;
  while (ros::ok()) {
    for (float i = 0; i < sNum; i += 1.0) {
      std::array<float, 2> point_ = csp_obj.calc_postion(i);

      pose.pose.position.x = point_[0];
      pose.pose.position.y = point_[1];
      pose.pose.position.z = 0;

      pose.pose.orientation.x = 0.0;
      pose.pose.orientation.y = 0.0;
      pose.pose.orientation.z = 0.0;
      pose.pose.orientation.w = 0.0;
      //   pose.pose.orientation.w = 0.0;
      now_path.poses.push_back(pose);
      // ROS_INFO("POSE WRITE IS OK!");
      struct Pose pose_file;
      pose_file.x = point_[0];
      pose_file.y = point_[1];
      poses.push_back(pose_file);
    }
    path_pubs_.publish(now_path);
    ros::spin();
    // loop_rate.sleep();
  }
  ROS_INFO("Update predefined pose file , and the data size is : %ld !! ", poses.size());
  std::string csv_path;
  sp.param<std::string>("csv_path", csv_path, "pre_path_file.csv");
  saveCsvFile(csv_path, poses);

  return 0;
}
