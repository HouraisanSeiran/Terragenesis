"""Exact area moments of clipped affine water over piecewise-constant beds."""

import numpy as np


def positive_affine_rectangle(depth_coefficients,bounds,velocity_coefficients=None):
    """Integrate h=max(a+b*x+c*z,0), and optional h*u, using clipped triangles."""
    xmin,xmax,zmin,zmax = bounds
    polygon = [np.array([xmin,zmin]),np.array([xmax,zmin]),np.array([xmax,zmax]),np.array([xmin,zmax])]
    coefficients = np.asarray(depth_coefficients)
    def value(point):
        return coefficients[0]+np.dot(coefficients[1:],point)
    clipped = []
    previous = polygon[-1]
    previous_value = value(previous)
    for current in polygon:
        current_value = value(current)
        if (current_value>=0) != (previous_value>=0):
            fraction = previous_value/(previous_value-current_value)
            clipped.append(previous+fraction*(current-previous))
        if current_value>=0:
            clipped.append(current)
        previous,previous_value = current,current_value
    volume = 0.
    momentum = np.zeros(2)
    if len(clipped)<3:
        return volume,momentum
    for number in range(1,len(clipped)-1):
        triangle = np.array([clipped[0],clipped[number],clipped[number+1]])
        first,second = triangle[1]-triangle[0],triangle[2]-triangle[0]
        area = abs(first[0]*second[1]-first[1]*second[0])/2
        h = np.maximum(coefficients[0]+triangle@coefficients[1:],0)
        volume += area*h.sum()/3
        if velocity_coefficients is not None:
            u = np.asarray(velocity_coefficients)[:,0][None,:]+triangle@np.asarray(velocity_coefficients)[:,1:].T
            momentum += area*(h.sum()*u.sum(axis=0)+(h[:,None]*u).sum(axis=0))/12
    return volume,momentum


def continuous_profile_moments(center,slope_x,slope_z,position_bed):
    """Canonical tile beds are constant; integrate each tile's linear free surface."""
    factor = position_bed.shape[1]
    count = len(center)
    volumes,momenta = np.zeros(count),np.zeros((count,2))
    edges = np.linspace(-.5,.5,factor+1)
    for cell in range(count):
        velocity = np.column_stack((center[cell,1:],slope_x[cell,1:],slope_z[cell,1:]))
        for row in range(factor):
            for column in range(factor):
                depth = [center[cell,0]-position_bed[cell,row,column],slope_x[cell,0],slope_z[cell,0]]
                bounds = (edges[column],edges[column+1],edges[row],edges[row+1])
                volume,momentum = positive_affine_rectangle(depth,bounds,velocity)
                volumes[cell] += volume
                momenta[cell] += momentum
    return volumes,momenta


def positive_affine_square_line(first,last,length=1.):
    """Exact integral of max(linear endpoint depths,0)^2 along an interface."""
    if first>=0 and last>=0:
        return length*(first*first+first*last+last*last)/3
    if first<=0 and last<=0:
        return 0.
    wet = max(first,last)
    return length*wet**3/(3*abs(last-first))


def exact_internal_jump_pressure(center,slope_x,slope_z,position_bed,spacing,gravity):
    factor = position_bed.shape[1]
    result = np.zeros((len(center),2))
    edges = np.linspace(-.5,.5,factor+1)
    for cell in range(len(center)):
        eta,sx,sz = center[cell,0],slope_x[cell,0],slope_z[cell,0]
        for direction in (0,1):
            for normal in range(1,factor):
                for tangent in range(factor):
                    if direction==0:
                        low_bed,high_bed = position_bed[cell,tangent,normal-1],position_bed[cell,tangent,normal]
                        first,last = eta+sx*edges[normal]+sz*edges[tangent],eta+sx*edges[normal]+sz*edges[tangent+1]
                    else:
                        low_bed,high_bed = position_bed[cell,normal-1,tangent],position_bed[cell,normal,tangent]
                        first,last = eta+sz*edges[normal]+sx*edges[tangent],eta+sz*edges[normal]+sx*edges[tangent+1]
                    high = positive_affine_square_line(first-high_bed,last-high_bed,1/factor)
                    low = positive_affine_square_line(first-low_bed,last-low_bed,1/factor)
                    result[cell,direction] += gravity*(high-low)/(2*spacing)
    return result
