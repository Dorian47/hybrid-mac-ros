#include <geometry_msgs/Twist.h>
#include <geometry_msgs/TwistStamped.h>
#include <nav_msgs/Path.h>
#include <ros/ros.h>
#include <tf/tf.h>
#include <tf/transform_broadcaster.h>

#include <algorithm>
#include <cassert>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "cpprobotics_types.h"
#include "cubic_spline.h"
#include "geometry_msgs/PoseStamped.h"

#define PREVIEW_DIS 3  // look-ahead distance
#define CONTROL_CYCLE 0.1
#define DEFAULT_VELOCITY 6  // default velocity (m/s), overridable via ROS param

#define Ld 1.868  // wheelbase

using namespace std;
using namespace cpprobotics;

ros::Publisher purepersuit_;
ros::Publisher path_pub_;
nav_msgs::Path path;

// File paths (configurable via ROS parameters)
std::string sequence_csv_file;
std::string output_lad_file;
std::string output_path_file;
double target_velocity = DEFAULT_VELOCITY;

float carVelocity = 0;
float preview_dis = PREVIEW_DIS;
float k = 0.1;
// For finding the current position according to waypoint.
int curr_index = 0;
int change_index = 0;
int pre_curr_index = 0;
float temp_dis = 0;
int loop_index = 0;
float pre_theta = 0.0;

auto currentPositionX = 0.0;
auto currentPositionY = 0.0;
auto currentPositionZ = 0.0;

auto currentQuaternionX = 0.0;
auto currentQuaternionY = 0.0;
auto currentQuaternionZ = 0.0;
auto currentQuaternionW = 0.0;

// Quaternion to Euler angle conversion
std::array<float, 3> calQuaternionToEuler(const float x, const float y,
                                          const float z, const float w) {
  std::array<float, 3> calRPY = {0.0f, 0.0f, 0.0f};
  // roll = atan2(2(wx+yz),1-2(x*x+y*y))
  calRPY[0] = atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y));
  // pitch = arcsin(2(wy-zx))
  calRPY[1] = asin(2 * (w * y - z * x));
  // yaw = atan2(2(wx+yz),1-2(y*y+z*z))
  calRPY[2] = atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));

  return calRPY;
}

std::array<float, 3> calRPY = {0.0f, 0.0f, 0.0f};

struct Pose
{
    int curr_index;
    double x;
    double y;
    double lad; // sqrt(pow(path_x - currentPositionX, 2) + pow(path_y - currentPositionY, 2));
    int change_index;  //change index according to discrete-time version
};
vector<Pose> poses_lad;
vector<Pose> poses_path;

 
void read_csv(const std::string& filename, std::vector<std::vector<std::string>>& data) {
    std::ifstream in(filename);
    std::string line;
    while (std::getline(in, line)) {
        std::stringstream ss(line);
        std::vector<std::string> row;
        std::string cell;
        while (std::getline(ss, cell, ',')) {
            row.push_back(cell);
        }
        data.push_back(row);
    }
}

void saveLadFile(std::string file_name, std::vector<Pose> path)
{
    std::ofstream outfile;
    outfile.open(file_name.c_str(), std::ios::trunc);
    outfile << "curr_index"
        << ","
        << "lad"
        << ","
        << "num" 
        << ","
        << "change_index" << std::endl;
    int num_count = 0;
    for (int i = 0; i < path.size(); ++i)
    {
        outfile << path.at(i).curr_index << "," << path.at(i).lad << "," << num_count << "," << path.at(i).change_index <<std::endl;
        num_count++;
    }
    outfile.close();
}

void savePathFile(std::string file_name, std::vector<Pose> path)
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

cpprobotics::Vec_f r_x_;
cpprobotics::Vec_f r_y_;

int pointNum = 0;  // number of path points
int targetIndex = pointNum - 1;
float min_lad = 100.0;
// Option 1
// vector<int> bestPoints_ = {pointNum - 1};
// Option 2
vector<float> bestPoints_ = {0.0};

// Compute steering command from current pose
void poseCallback(const geometry_msgs::PoseStamped &currentWaypoint) {
  currentPositionX = currentWaypoint.pose.position.x;
  currentPositionY = currentWaypoint.pose.position.y;
  currentPositionZ = 0.0;

  currentQuaternionX = currentWaypoint.pose.orientation.x;
  currentQuaternionY = currentWaypoint.pose.orientation.y;
  currentQuaternionZ = currentWaypoint.pose.orientation.z;
  currentQuaternionW = currentWaypoint.pose.orientation.w;

  calRPY = calQuaternionToEuler(currentQuaternionX, currentQuaternionY,
                           currentQuaternionZ, currentQuaternionW);
  struct Pose pose_path;
  pose_path.x = currentPositionX;
  pose_path.y = currentPositionY;
  poses_path.push_back(pose_path);
}

void velocityCall(const geometry_msgs::TwistStamped &carWaypoint) {
  // carVelocity = carWaypoint.linear.x;
  carVelocity = carWaypoint.twist.linear.x;
  // ROS_INFO("The carVelocity is : [%f]. ",carVelocity);
  preview_dis = k * carVelocity + PREVIEW_DIS;
}

void pointCallback(const nav_msgs::Path &msg) {
  // geometry_msgs/PoseStamped[] poses
  pointNum = msg.poses.size();

  // auto a = msg.poses[0].pose.position.x;
  for (int i = 0; i < pointNum; i++) {
    r_x_.push_back(msg.poses[i].pose.position.x);
    r_y_.push_back(msg.poses[i].pose.position.y);
  }
}

void executeLoop(){
  // Find the closest waypoint to current position
  int index;
  vector<float> bestPoints_;
  for (int i = 0; i < pointNum; i++) {
    float path_x = r_x_[i];
    float path_y = r_y_[i];
    // Compute distance from current position to each waypoint
    float lad = sqrt(pow(path_x - currentPositionX, 2) +
                     pow(path_y - currentPositionY, 2));

    bestPoints_.push_back(lad);
  }
  // Find the minimum lateral distance and its waypoint index.
  auto smallest = min_element(bestPoints_.begin(), bestPoints_.end());
  index = distance(bestPoints_.begin(), smallest);
  curr_index = index;
  temp_dis = bestPoints_.at(curr_index);
  // ROS_INFO("Update executeLoop !!22222 index: [%d] ", index);
  
  // Find the min_dis waypoint with curr_index.
  if(pre_curr_index == curr_index){
    float lad = sqrt(pow(r_x_[curr_index] - currentPositionX, 2) +
                     pow(r_y_[curr_index] - currentPositionY, 2));
    if(lad < min_lad){
      min_lad = lad;
    }
    // ROS_INFO("Curr_index : [%d], and lad is : [%f]. ",curr_index, lad);
  }else{
    // auto smallest = min_element(points_with_same_index.begin(), points_with_same_index.end());
    struct Pose pose_lad;
    ROS_INFO("Pre_index: [%d], Curr_index : [%d], and min_lad is : [%f], and change_index: [%d]. ",pre_curr_index, curr_index, min_lad, change_index);
    pose_lad.lad = min_lad;
    pose_lad.curr_index = pre_curr_index;
    pose_lad.change_index = change_index;
    poses_lad.push_back(pose_lad);
    pre_curr_index = curr_index;
    min_lad = 100.0;
  }
  // ROS_INFO("Update executeLoop !!33333 index: [%d] ", index);
  
  int temp_index = index;
  for (int i = index; i < pointNum; i++) {
    float dis =
        sqrt(pow(r_y_[index] - r_y_[i], 2) + pow(r_x_[index] - r_x_[i], 2));
    if (dis < preview_dis) {
      temp_index = i;
    } else {
      break;
    }
  }
  // ROS_INFO("Update executeLoop !!4444 index: [%d] and pointNum : [%d] ", index, temp_index);
  
  index = temp_index;
  /**************************************************************************************************/
  // ROS_INFO("Current index : [%d], and currentPositionY is : [%f], and r_y_[index] is : [%f], and the temp_dis: [%f]. ",curr_index, currentPositionY, r_y_[curr_index], temp_dis);
  float alpha =
      atan2(r_y_[index] - currentPositionY, r_x_[index] - currentPositionX) -
      calRPY[2];

  // Distance between the current pose and target waypoint.
  float dl = sqrt(pow(r_y_[index] - currentPositionY, 2) +
                  pow(r_x_[index] - currentPositionX, 2));
  // If the distance between current position and waypoint is smaller than v*T,
  // then pursue the next waypoint.
  // if(r_x_[curr_index] - currentPositionX < 0){

  // }
  float new_velocity = target_velocity;

  ROS_INFO("The pointNum: [%d], and the dl is:[%f]. ",pointNum, dl);
  if (dl > 0.4 && curr_index < pointNum - 1) {
    float theta = atan(2 * Ld * sin(alpha) / dl);
    geometry_msgs::Twist vel_msg;
    std::vector<std::vector<std::string>> seq_data;

    read_csv(sequence_csv_file, seq_data);
    if (loop_index >= (int)seq_data.size()) {
      ROS_WARN("Sequence CSV exhausted at index %d, stopping.", loop_index);
      geometry_msgs::Twist vel_msg;
      vel_msg.linear.x = 0;
      vel_msg.angular.z = 0;
      purepersuit_.publish(vel_msg);
      path_pub_.publish(path);
      return;
    }
    int cmd_seq = std::stoi(seq_data[loop_index][1]);
    ROS_INFO("Current index: %d, Cmd_seq is : %d ! ",loop_index , cmd_seq);
    if(cmd_seq == 0){
      vel_msg.linear.x = new_velocity;
      vel_msg.angular.z = theta;
      pre_theta = theta;
    }
    else{
      vel_msg.linear.x = new_velocity;
      vel_msg.angular.z = pre_theta;
    }
    purepersuit_.publish(vel_msg);
    // Publish trajectory visualization
    geometry_msgs::PoseStamped this_pose_stamped;
    this_pose_stamped.pose.position.x = currentPositionX;
    this_pose_stamped.pose.position.y = currentPositionY;

    geometry_msgs::Quaternion goal_quat = tf::createQuaternionMsgFromYaw(theta);
    this_pose_stamped.pose.orientation.x = currentQuaternionX;
    this_pose_stamped.pose.orientation.y = currentQuaternionY;
    this_pose_stamped.pose.orientation.z = currentQuaternionZ;
    this_pose_stamped.pose.orientation.w = currentQuaternionW;

    this_pose_stamped.header.stamp = ros::Time::now();

    this_pose_stamped.header.frame_id = "world";
    path.poses.push_back(this_pose_stamped);
  } else {
    geometry_msgs::Twist vel_msg;
    vel_msg.linear.x = 0;
    vel_msg.angular.z = 0;
    purepersuit_.publish(vel_msg);
  }
  path_pub_.publish(path);
  loop_index++;
}


int main(int argc, char **argv) {
  ros::init(argc, argv, "pure_pursuit");
  ros::NodeHandle n;
  ros::NodeHandle nh("~");  // private parameters

  // Load file paths from ROS parameters (or use defaults)
  nh.param<std::string>("sequence_csv", sequence_csv_file,
                        "sequence_data_tdma.csv");
  nh.param<std::string>("output_lad", output_lad_file,
                        "true_lad_file.csv");
  nh.param<std::string>("output_path", output_path_file,
                        "true_path_file.csv");
  nh.param<double>("velocity", target_velocity, (double)DEFAULT_VELOCITY);
  ROS_INFO("Sequence CSV: %s, Velocity: %.1f m/s", sequence_csv_file.c_str(), target_velocity);

  purepersuit_ = n.advertise<geometry_msgs::Twist>("/smart/cmd_vel", 20);

  path_pub_ = n.advertise<nav_msgs::Path>("rvizpath", 100, true);
  //ros::Rate loop_rate(10);

  path.header.frame_id = "world";
  path.header.stamp = ros::Time::now();
  geometry_msgs::PoseStamped pose;
  pose.header.stamp = ros::Time::now();
  pose.header.frame_id = "world";

  ros::Subscriber splinePath = n.subscribe("/splinepoints", 20, pointCallback);
  ros::Subscriber carVel = n.subscribe("/smart/velocity", 20, velocityCall);
  ros::Subscriber carPose = n.subscribe("/smart/rear_pose", 20, poseCallback);
  ros::Timer timer_ = n.createTimer(ros::Duration(CONTROL_CYCLE), boost::bind(executeLoop));

  ros::spin();
  ROS_INFO("Update true pose file , and the data size is : %ld !! ", poses_lad.size());
  saveLadFile(output_lad_file, poses_lad);
  savePathFile(output_path_file, poses_path);
  return 0;
}
