/*
 * @Author: PurePursuit example authors
 * @Date: 2021-09-20 17:03:11
 * @LastEditTime: 2021-09-20 19:59:44
 * @LastEditors: Open-source release cleanup
 * @Description: In User Settings Edit
 * @FilePath: /littice/include/cpprobotics_types.h
 */

#ifndef _CPPROBOTICS_TYPES_H
#define _CPPROBOTICS_TYPES_H

#include<iterator>
#include<vector>
#include<array>
#include<string>
#include<iostream>

namespace cpprobotics{

using Vec_f=std::vector<float>;
using Poi_f=std::array<float, 2>;
using Vec_Poi=std::vector<Poi_f>;

};

#endif
